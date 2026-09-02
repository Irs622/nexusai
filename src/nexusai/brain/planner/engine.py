"""PlanGraphExecutionEngine with IGovernancePort admission control, PriorityScheduler dispatch, durable checkpointing, and IObservabilityPort telemetry."""

from __future__ import annotations

import asyncio
import graphlib
import time
from typing import Any

from nexusai.brain.domain.agent import (
    DecisionTrace,
    ExecutionFailure,
    FailureReason,
    PlanGraph,
    PlanningContext,
    StepStatus,
)
from nexusai.brain.domain.execution_state import (
    ExecutionRecord,
    ExecutionStatus,
    NodeExecutionRecord,
    NodeExecutionStatus,
    compute_plan_graph_hash,
)
from nexusai.brain.domain.governance import (
    GovernanceDecision,
    GovernanceRequest,
    ResourceRequest,
    ToolCapability,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.domain.recovery import (
    FailureClass,
    RecoveryAction,
    RecoveryDecision,
    RecoveryPolicyEngine,
    ToolExecutionPolicy,
    classify_failure,
    generate_idempotency_key,
)
from nexusai.brain.domain.scheduler import ScheduledTask, TaskPriority
from nexusai.brain.planner.stages import ExecutionPlanner, RecoveryPlanner
from nexusai.brain.planner.validator import PlanValidator
from nexusai.brain.ports.execution_state_port import IExecutionStateStore
from nexusai.brain.ports.governance_port import IGovernancePort
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.reconciliation_port import DefaultReconciliationAdapter, IReconciliationPort
from nexusai.brain.ports.scheduler_port import IScheduler
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker, ExecutionPolicy
from nexusai.brain.runtime.governance_engine import DEFAULT_TOOL_CAPABILITIES, GovernanceEngine
from nexusai.brain.runtime.priority_scheduler import PriorityScheduler


class PlanGraphExecutionEngine:
    """Bounded concurrent DAG execution engine with IGovernancePort admission control, telemetry emissions, and durable checkpointing."""

    def __init__(
        self,
        planner: ExecutionPlanner | None = None,
        validator: PlanValidator | None = None,
        recovery_planner: RecoveryPlanner | None = None,
        policy: ExecutionPolicy | None = None,
        state_store: IExecutionStateStore | None = None,
        reconciler: IReconciliationPort | None = None,
        scheduler: IScheduler | None = None,
        governance: IGovernancePort | None = None,
        telemetry: IObservabilityPort | None = None,
        tool_policies: dict[str, ToolExecutionPolicy] | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.planner = planner or ExecutionPlanner()
        self.validator = validator or PlanValidator()
        self.recovery_planner = recovery_planner or RecoveryPlanner()
        self.policy = policy or ExecutionPolicy()
        self.circuit_breaker = CircuitBreaker()
        self.state_store = state_store
        self.reconciler = reconciler or DefaultReconciliationAdapter()
        self.telemetry = telemetry
        self.governance = governance or GovernanceEngine(telemetry=telemetry)
        self.scheduler = scheduler or PriorityScheduler(aging_rate=0.5, telemetry=telemetry)
        self.tool_policies = tool_policies or {}
        self.max_concurrency = max_concurrency

    def get_tool_policy(self, tool_name: str | None) -> ToolExecutionPolicy:
        """Fetch configured ToolExecutionPolicy for a tool or fallback to default policy."""
        if tool_name and tool_name in self.tool_policies:
            return self.tool_policies[tool_name]
        return ToolExecutionPolicy()

    def get_required_capabilities(self, tool_name: str | None) -> frozenset[ToolCapability]:
        """Fetch declared capabilities for a tool or return empty set for default tools."""
        if not tool_name:
            return frozenset()
        caps = DEFAULT_TOOL_CAPABILITIES.get(tool_name, set())
        return frozenset(caps)

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        exec_id: str | None = None,
        node_id: str | None = None,
        task_id: str | None = None,
        attempt: int | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"evt-{event_type.value}-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                execution_id=exec_id,
                node_id=str(node_id) if node_id is not None else None,
                task_id=task_id,
                attempt=attempt,
                attributes=attributes or {},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def _safe_telemetry_counter(self, name: str, value: int = 1, attributes: dict[str, Any] | None = None) -> None:
        if not self.telemetry:
            return
        try:
            await self.telemetry.increment_counter(name, value, attributes=attributes)
        except Exception:
            pass

    async def _safe_telemetry_duration(self, name: str, duration_ms: float, attributes: dict[str, Any] | None = None) -> None:
        if not self.telemetry:
            return
        try:
            await self.telemetry.record_duration(name, duration_ms, attributes=attributes)
        except Exception:
            pass

    def get_topological_execution_order(self, plan_graph: PlanGraph) -> list[Any]:
        """Derive deterministic topological execution order for PlanGraph DAG nodes."""
        for node_id, node in plan_graph.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in plan_graph.nodes:
                    raise RuntimeError(
                        f"Dependency step {dep_id} required by step {node_id} is missing from PlanGraph"
                    )

        graph_deps: dict[Any, set[Any]] = {
            node_id: set(node.dependencies) for node_id, node in plan_graph.nodes.items()
        }

        ts = graphlib.TopologicalSorter(graph_deps)
        try:
            ts.prepare()
        except graphlib.CycleError as cycle_err:
            raise RuntimeError(
                f"PlanGraph contains a dependency cycle: {cycle_err}"
            ) from cycle_err

        execution_order: list[Any] = []
        while ts.is_active():
            ready_nodes = ts.get_ready()
            if not ready_nodes:
                break
            sorted_ready = sorted(ready_nodes, key=lambda n: (type(n).__name__, str(n)))
            for node_id in sorted_ready:
                execution_order.append(node_id)
                ts.done(node_id)

        return execution_order

    async def execute_plan(
        self,
        ctx: PlanningContext,
        tool_port: IToolPort,
        session_id: str = "session-1",
        max_concurrency: int | None = None,
        execution_id: str | None = None,
    ) -> tuple[PlanGraph, list[ToolExecutionResult], DecisionTrace]:
        """Execute PlanningContext through Planner, PlanValidator, and ToolPort with IGovernancePort admission."""
        t_exec_start = time.perf_counter()
        plan_graph, trace = self.planner.plan(ctx, session_id=session_id)

        val_result = self.validator.validate(plan_graph, constraints=ctx.constraints_component)
        if not val_result.is_valid:
            raise RuntimeError(
                f"PlanGraph validation failed: {[i.message for i in val_result.issues]}"
            )

        for node_id, node in plan_graph.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in plan_graph.nodes:
                    raise RuntimeError(
                        f"Dependency step {dep_id} required by step {node_id} is missing from PlanGraph"
                    )

        graph_hash = compute_plan_graph_hash(plan_graph)
        exec_id = execution_id or f"exec-{int(time.time() * 1000)}"

        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_STARTED, exec_id=exec_id)
        await self._safe_telemetry_counter("nexusai_executions_total")

        if self.state_store is not None:
            node_records = {}
            for n_id, n_obj in plan_graph.nodes.items():
                idempotency_key = generate_idempotency_key(exec_id, n_id)
                node_records[n_id] = NodeExecutionRecord(
                    execution_id=exec_id,
                    node_id=n_id,
                    status=NodeExecutionStatus.PENDING,
                    tool_name=n_obj.step.tool_name,
                    arguments=n_obj.step.arguments,
                    idempotency_key=idempotency_key,
                )
            exec_record = ExecutionRecord(
                execution_id=exec_id,
                plan_id=session_id,
                graph_hash=graph_hash,
                status=ExecutionStatus.RUNNING,
                node_records=node_records,
            )
            try:
                await self._safe_telemetry_event(RuntimeEventType.CHECKPOINT_STARTED, exec_id=exec_id)
                await self.state_store.create_execution(exec_record)
                await self._safe_telemetry_event(RuntimeEventType.CHECKPOINT_COMPLETED, exec_id=exec_id)
                await self._safe_telemetry_counter("nexusai_checkpoint_writes_total")
            except Exception:
                await self._safe_telemetry_event(RuntimeEventType.CHECKPOINT_FAILED, exec_id=exec_id)
                await self._safe_telemetry_counter("nexusai_checkpoint_failures_total")
                raise

        if getattr(self.scheduler, "_is_shutdown", False):
            self.scheduler = PriorityScheduler(aging_rate=0.5, telemetry=self.telemetry)

        res_tuple = await self._run_dag_execution(
            plan_graph=plan_graph,
            trace=trace,
            tool_port=tool_port,
            exec_id=exec_id,
            max_concurrency=max_concurrency,
        )

        exec_dur_ms = (time.perf_counter() - t_exec_start) * 1000.0
        await self._safe_telemetry_duration("nexusai_execution_duration_ms", exec_dur_ms)
        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_COMPLETED, exec_id=exec_id)
        await self._safe_telemetry_counter("nexusai_executions_completed_total")

        return res_tuple

    async def resume_execution(
        self,
        execution_id: str,
        ctx: PlanningContext,
        tool_port: IToolPort,
        session_id: str = "session-1",
        max_concurrency: int | None = None,
    ) -> tuple[PlanGraph, list[ToolExecutionResult], DecisionTrace]:
        """Resume an interrupted execution after process restart using governance and checkpoints."""
        t_exec_start = time.perf_counter()
        if self.state_store is None:
            raise RuntimeError("Cannot resume execution: No state_store configured on PlanGraphExecutionEngine")

        exec_record = await self.state_store.load_execution(execution_id)
        if exec_record is None:
            raise RuntimeError(f"Execution record '{execution_id}' not found in state store")

        plan_graph, trace = self.planner.plan(ctx, session_id=session_id)

        current_hash = compute_plan_graph_hash(plan_graph)
        if current_hash != exec_record.graph_hash:
            raise RuntimeError(
                f"Plan mismatch: Stored hash '{exec_record.graph_hash[:8]}' does not match current plan hash '{current_hash[:8]}'"
            )

        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_STARTED, exec_id=execution_id)
        await self._safe_telemetry_counter("nexusai_executions_total")

        cached_results: list[ToolExecutionResult] = []
        completed_nodes: set[Any] = set()

        for n_id, n_obj in plan_graph.nodes.items():
            n_rec = exec_record.node_records.get(n_id)
            if n_rec is not None:
                if n_rec.status == NodeExecutionStatus.COMPLETED:
                    n_obj.step.status = StepStatus.COMPLETED
                    completed_nodes.add(n_id)
                    if n_rec.tool_name:
                        cached_results.append(
                            ToolExecutionResult(
                                request_id=f"step-{n_obj.step.step_id}",
                                tool_name=n_rec.tool_name,
                                success=True,
                                output=n_rec.output,
                                error_message=n_rec.error_message,
                            )
                        )
                elif n_rec.status in (NodeExecutionStatus.RUNNING, NodeExecutionStatus.RETRY_WAIT):
                    n_obj.step.status = StepStatus.PENDING
                elif n_rec.status == NodeExecutionStatus.FAILED:
                    n_obj.step.status = StepStatus.FAILED
                elif n_rec.status == NodeExecutionStatus.CANCELLED:
                    n_obj.step.status = StepStatus.CANCELLED

        res_tuple = await self._run_dag_execution(
            plan_graph=plan_graph,
            trace=trace,
            tool_port=tool_port,
            exec_id=execution_id,
            max_concurrency=max_concurrency,
            pre_completed_nodes=completed_nodes,
            pre_results=cached_results,
            node_records_cache=exec_record.node_records,
        )

        exec_dur_ms = (time.perf_counter() - t_exec_start) * 1000.0
        await self._safe_telemetry_duration("nexusai_execution_duration_ms", exec_dur_ms)
        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_COMPLETED, exec_id=execution_id)
        await self._safe_telemetry_counter("nexusai_executions_completed_total")

        return res_tuple

    async def _run_dag_execution(
        self,
        plan_graph: PlanGraph,
        trace: DecisionTrace,
        tool_port: IToolPort,
        exec_id: str,
        max_concurrency: int | None = None,
        pre_completed_nodes: set[Any] | None = None,
        pre_results: list[ToolExecutionResult] | None = None,
        node_records_cache: dict[Any, NodeExecutionRecord] | None = None,
    ) -> tuple[PlanGraph, list[ToolExecutionResult], DecisionTrace]:
        """Internal concurrent execution loop with IGovernancePort admission control."""
        graph_deps: dict[Any, set[Any]] = {
            node_id: set(node.dependencies) for node_id, node in plan_graph.nodes.items()
        }

        ts = graphlib.TopologicalSorter(graph_deps)
        ts.prepare()

        limit = max_concurrency if max_concurrency is not None else self.max_concurrency
        semaphore = asyncio.Semaphore(limit)

        results: list[ToolExecutionResult] = list(pre_results or [])
        completed_nodes: set[Any] = set(pre_completed_nodes or [])
        failed_nodes: set[Any] = set()

        cb_lock = asyncio.Lock()
        results_lock = asyncio.Lock()
        active_tasks: dict[asyncio.Task[None], Any] = {}

        attempt_counts: dict[Any, int] = {}
        if node_records_cache:
            for nid, nrec in node_records_cache.items():
                attempt_counts[nid] = nrec.attempt_count

        for comp_id in completed_nodes:
            if comp_id in plan_graph.nodes:
                try:
                    ts.done(comp_id)
                except ValueError:
                    pass

        async def _run_single_node(node_id: Any) -> None:
            async with semaphore:
                t_node_start = time.perf_counter()
                node = plan_graph.nodes[node_id]

                for dep_id in node.dependencies:
                    if dep_id not in completed_nodes:
                        node.step.status = StepStatus.CANCELLED
                        failed_nodes.add(node_id)
                        await self._safe_telemetry_event(RuntimeEventType.NODE_CANCELLED, exec_id=exec_id, node_id=str(node_id))
                        await self._safe_telemetry_counter("nexusai_nodes_cancelled_total")
                        if self.state_store:
                            await self.state_store.mark_node_cancelled(exec_id, node_id)
                        raise RuntimeError(
                            f"Dependency step {dep_id} failed or incomplete before step {node_id}"
                        )

                step = node.step
                idempotency_key = generate_idempotency_key(exec_id, node_id)
                policy = self.get_tool_policy(step.tool_name)

                while True:
                    current_attempt = attempt_counts.get(node_id, 0) + 1
                    attempt_counts[node_id] = current_attempt

                    step.status = StepStatus.RUNNING
                    await self._safe_telemetry_event(RuntimeEventType.NODE_STARTED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                    await self._safe_telemetry_counter("nexusai_nodes_total")
                    if self.state_store:
                        await self.state_store.mark_node_running(exec_id, node_id)

                    if not step.tool_name:
                        if self.state_store:
                            dummy_res = ToolExecutionResult(
                                request_id=f"step-{step.step_id}",
                                tool_name="none",
                                success=True,
                                output="No tool step",
                            )
                            await self.state_store.save_node_result_atomically(
                                exec_id, node_id, NodeExecutionStatus.COMPLETED, dummy_res
                            )
                        step.status = StepStatus.COMPLETED
                        completed_nodes.add(node_id)
                        await self._safe_telemetry_event(RuntimeEventType.NODE_COMPLETED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                        await self._safe_telemetry_counter("nexusai_nodes_completed_total")
                        break

                    # --- IGovernancePort Admission Control ---
                    req_caps = self.get_required_capabilities(step.tool_name)
                    gov_req = GovernanceRequest(
                        execution_id=exec_id,
                        node_id=str(node_id),
                        tool_name=step.tool_name,
                        required_capabilities=req_caps,
                        resource_request=ResourceRequest(tool_invocations=1),
                    )

                    decision = await self.governance.authorize(gov_req)

                    if not decision.allowed:
                        # Governance Denial Invariant: Governance denials DO NOT enter exponential retries
                        fail_gov_res = ToolExecutionResult(
                            request_id=f"step-{step.step_id}",
                            tool_name=step.tool_name,
                            success=False,
                            error_message=f"Governance denied execution ({decision.reason})",
                        )
                        if self.state_store:
                            await self.state_store.save_node_result_atomically(
                                exec_id, node_id, NodeExecutionStatus.FAILED, fail_gov_res
                            )
                        step.status = StepStatus.FAILED
                        async with results_lock:
                            results.append(fail_gov_res)
                        failed_nodes.add(node_id)
                        await self._safe_telemetry_event(RuntimeEventType.NODE_FAILED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt, attributes={"reason": decision.reason})
                        await self._safe_telemetry_counter("nexusai_nodes_failed_total")
                        break

                    # Resource Reservation Release Lifecycle Invariant
                    try:
                        cb_open = False
                        async with cb_lock:
                            if self.circuit_breaker.state.value == "OPEN":
                                cb_open = True
                                await self._safe_telemetry_event(RuntimeEventType.CIRCUIT_BREAKER_OPEN, exec_id=exec_id, node_id=str(node_id))

                        req = ToolExecutionRequest(
                            tool_name=step.tool_name,
                            arguments=step.arguments,
                            execution_id=f"step-{step.step_id}",
                        )

                        t0 = time.perf_counter()
                        exec_err: Exception | None = None
                        res: ToolExecutionResult | None = None

                        await self._safe_telemetry_event(RuntimeEventType.TOOL_STARTED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt, attributes={"tool_name": step.tool_name})
                        await self._safe_telemetry_counter("nexusai_tool_executions_total", attributes={"tool_name": step.tool_name})

                        try:
                            if cb_open:
                                raise RuntimeError("CircuitBreaker is OPEN")
                            res = await tool_port.execute(req)
                            t_tool_dur_ms = (time.perf_counter() - t0) * 1000.0
                            await self._safe_telemetry_duration("nexusai_tool_duration_ms", t_tool_dur_ms, attributes={"tool_name": step.tool_name})
                        except Exception as err:
                            exec_err = err

                        if res and res.success:
                            await self._safe_telemetry_event(RuntimeEventType.TOOL_COMPLETED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt, attributes={"tool_name": step.tool_name})
                            if self.state_store:
                                await self.state_store.save_node_result_atomically(
                                    exec_id, node_id, NodeExecutionStatus.COMPLETED, res
                                )
                            async with cb_lock:
                                self.circuit_breaker.record_success()
                            step.status = StepStatus.COMPLETED
                            async with results_lock:
                                results.append(res)
                            completed_nodes.add(node_id)

                            node_dur_ms = (time.perf_counter() - t_node_start) * 1000.0
                            await self._safe_telemetry_duration("nexusai_node_duration_ms", node_dur_ms)
                            await self._safe_telemetry_event(RuntimeEventType.NODE_COMPLETED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                            await self._safe_telemetry_counter("nexusai_nodes_completed_total")
                            break

                        err_msg = res.error_message if res else (str(exec_err) if exec_err else "Unknown error")
                        f_class = classify_failure(exec_err, err_msg)
                        await self._safe_telemetry_event(RuntimeEventType.RECOVERY_CLASSIFIED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt, attributes={"failure_class": f_class.value})

                        decision_rec = RecoveryPolicyEngine.evaluate(
                            policy=policy,
                            failure_class=f_class,
                            attempt_number=current_attempt,
                            idempotency_key=idempotency_key,
                            cb_is_open=cb_open,
                        )

                        if decision_rec.action == RecoveryAction.RETRY:
                            await self._safe_telemetry_event(RuntimeEventType.RECOVERY_RETRY, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt, attributes={"failure_class": f_class.value, "retry_delay": decision_rec.retry_delay_seconds})
                            await self._safe_telemetry_counter("nexusai_recovery_retries_total", attributes={"failure_class": f_class.value})
                            await self._safe_telemetry_duration("nexusai_recovery_backoff_ms", decision_rec.retry_delay_seconds * 1000.0)

                            if self.state_store:
                                await self.state_store.save_recovery_decision_atomically(
                                    exec_id, node_id, NodeExecutionStatus.RETRY_WAIT, decision_rec
                                )
                            
                            retry_task = ScheduledTask(
                                task_id=f"{exec_id}:{node_id}:retry-{current_attempt}",
                                execution_id=exec_id,
                                node_id=node_id,
                                priority=TaskPriority.HIGH if policy.idempotent else TaskPriority.NORMAL,
                                delay_until=decision_rec.next_retry_at,
                            )
                            await self.scheduler.submit(retry_task)
                            
                            claimed_retry = await self.scheduler.next()
                            if claimed_retry.task_id != retry_task.task_id:
                                pass
                            continue

                        elif decision_rec.action == RecoveryAction.RECONCILE:
                            await self._safe_telemetry_event(RuntimeEventType.RECOVERY_RECONCILIATION_REQUIRED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                            await self._safe_telemetry_counter("nexusai_recovery_reconciliations_total")

                            if self.state_store:
                                await self.state_store.save_recovery_decision_atomically(
                                    exec_id, node_id, NodeExecutionStatus.RECONCILIATION_REQUIRED, decision_rec
                                )
                            
                            rec_outcome: ToolExecutionResult | None = None
                            if self.reconciler:
                                try:
                                    rec_outcome = await self.reconciler.reconcile(exec_id, node_id, idempotency_key)
                                except Exception:
                                    rec_outcome = None

                            if rec_outcome and rec_outcome.success:
                                await self._safe_telemetry_event(RuntimeEventType.RECOVERY_RECONCILIATION_COMPLETED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                                if self.state_store:
                                    await self.state_store.save_node_result_atomically(
                                        exec_id, node_id, NodeExecutionStatus.COMPLETED, rec_outcome
                                    )
                                async with cb_lock:
                                    self.circuit_breaker.record_success()
                                step.status = StepStatus.COMPLETED
                                async with results_lock:
                                    results.append(rec_outcome)
                                completed_nodes.add(node_id)

                                node_dur_ms = (time.perf_counter() - t_node_start) * 1000.0
                                await self._safe_telemetry_duration("nexusai_node_duration_ms", node_dur_ms)
                                await self._safe_telemetry_event(RuntimeEventType.NODE_COMPLETED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                                await self._safe_telemetry_counter("nexusai_nodes_completed_total")
                                break
                            else:
                                await self._safe_telemetry_event(RuntimeEventType.RECOVERY_FAILED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                                fail_res = ToolExecutionResult(
                                    request_id=f"step-{step.step_id}",
                                    tool_name=step.tool_name,
                                    success=False,
                                    error_message=f"Reconciliation required for non-idempotent operation: {decision_rec.reason}",
                                )
                                if self.state_store:
                                    await self.state_store.save_node_result_atomically(
                                        exec_id, node_id, NodeExecutionStatus.FAILED, fail_res
                                    )
                                async with cb_lock:
                                    self.circuit_breaker.record_failure()
                                step.status = StepStatus.FAILED
                                async with results_lock:
                                    results.append(fail_res)
                                failed_nodes.add(node_id)

                                await self._safe_telemetry_event(RuntimeEventType.NODE_FAILED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                                await self._safe_telemetry_counter("nexusai_nodes_failed_total")
                                break

                        else:
                            async with cb_lock:
                                self.circuit_breaker.record_failure()

                            fail_res = res or ToolExecutionResult(
                                request_id=f"step-{step.step_id}",
                                tool_name=step.tool_name,
                                success=False,
                                error_message=f"Execution failed ({decision_rec.failure_class.value}): {decision_rec.reason}",
                            )
                            target_status = (
                                NodeExecutionStatus.CANCELLED
                                if decision_rec.action == RecoveryAction.CANCEL
                                else NodeExecutionStatus.FAILED
                            )
                            if self.state_store:
                                await self.state_store.save_recovery_decision_atomically(
                                    exec_id, node_id, target_status, decision_rec
                                )
                                await self.state_store.save_node_result_atomically(
                                    exec_id, node_id, target_status, fail_res
                                )

                            step.status = StepStatus.CANCELLED if decision_rec.action == RecoveryAction.CANCEL else StepStatus.FAILED
                            async with results_lock:
                                results.append(fail_res)
                            failed_nodes.add(node_id)

                            await self._safe_telemetry_event(RuntimeEventType.NODE_FAILED, exec_id=exec_id, node_id=str(node_id), attempt=current_attempt)
                            await self._safe_telemetry_counter("nexusai_nodes_failed_total")
                            break
                    finally:
                        # Resource Release Invariant: Always release reservation regardless of execution outcome
                        if decision.reservation_id:
                            await self.governance.release(decision.reservation_id)

        try:
            while ts.is_active():
                ready = list(ts.get_ready())
                if ready:
                    unexecuted_ready = [n for n in ready if n not in completed_nodes]
                    for node_id in unexecuted_ready:
                        stask = ScheduledTask(
                            task_id=f"{exec_id}:{node_id}",
                            execution_id=exec_id,
                            node_id=node_id,
                            priority=TaskPriority.NORMAL,
                        )
                        await self.scheduler.submit(stask)
                break

            while True:
                ready_cnt = await self.scheduler.get_ready_count()
                sched_size = await self.scheduler.size()

                if sched_size == 0 and not active_tasks:
                    break

                if ready_cnt > 0 or (sched_size > 0 and len(active_tasks) < limit):
                    try:
                        claimed = await self.scheduler.next()
                        task = asyncio.create_task(_run_single_node(claimed.node_id))
                        active_tasks[task] = claimed.node_id
                    except SchedulerClosedError:
                        break

                if not active_tasks:
                    break

                done, pending = await asyncio.wait(
                    active_tasks.keys(), return_when=asyncio.FIRST_COMPLETED
                )

                for finished_task in done:
                    node_id = active_tasks.pop(finished_task)
                    try:
                        await finished_task
                        if node_id in completed_nodes:
                            ts.done(node_id)
                            if ts.is_active():
                                new_ready = list(ts.get_ready())
                                for n_id in new_ready:
                                    if n_id not in completed_nodes:
                                        stask = ScheduledTask(
                                            task_id=f"{exec_id}:{n_id}",
                                            execution_id=exec_id,
                                            node_id=n_id,
                                            priority=TaskPriority.NORMAL,
                                        )
                                        await self.scheduler.submit(stask)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            for task in list(active_tasks.keys()):
                if not task.done():
                    task.cancel()
            if active_tasks:
                await asyncio.gather(*active_tasks.keys(), return_exceptions=True)
            if self.state_store:
                await self.state_store.update_execution_status(exec_id, ExecutionStatus.CANCELLED)
            await self._safe_telemetry_event(RuntimeEventType.EXECUTION_CANCELLED, exec_id=exec_id)
            await self._safe_telemetry_counter("nexusai_executions_cancelled_total")
            await self.scheduler.shutdown()
            raise

        overall_status = ExecutionStatus.COMPLETED if not failed_nodes else ExecutionStatus.FAILED
        if self.state_store:
            await self.state_store.update_execution_status(exec_id, overall_status)

        if overall_status == ExecutionStatus.FAILED:
            await self._safe_telemetry_event(RuntimeEventType.EXECUTION_FAILED, exec_id=exec_id)
            await self._safe_telemetry_counter("nexusai_executions_failed_total")

        await self.scheduler.shutdown()
        return plan_graph, results, trace
