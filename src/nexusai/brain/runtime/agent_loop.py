"""AgentLoop runtime implementation providing governed Planning -> Execution -> Observation loop control."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanGraph,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.domain.agent_loop import (
    TERMINAL_LOOP_STATES,
    AgentLoopConfig,
    AgentLoopResult,
    AgentLoopState,
    LoopDecision,
    Observation,
    compute_plan_fingerprint,
)
from nexusai.brain.domain.agent_runtime import AgentRequest
from nexusai.brain.domain.memory import MemoryEntry, MemoryProvenance, MemoryType
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.domain.tool_registry import ToolMetadata
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.agent_loop_port import IAgentLoop
from nexusai.brain.ports.llm_provider_port import ILLMProvider
from nexusai.brain.ports.memory_port import IContextBuilder, IMemoryStore
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.outcome_evaluator_port import IOutcomeEvaluator
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionResult
from nexusai.brain.ports.tool_registry_port import IToolRegistry
from nexusai.brain.runtime.deterministic_evaluator import DeterministicOutcomeEvaluator


class AgentLoop(IAgentLoop):
    """Governed Agent Loop controller implementing Planning -> Execution -> Observation state machine."""

    def __init__(
        self,
        execution_engine: PlanGraphExecutionEngine | None = None,
        tool_registry: IToolRegistry | None = None,
        llm_provider: ILLMProvider | None = None,
        context_builder: IContextBuilder | None = None,
        memory_store: IMemoryStore | None = None,
        evaluator: IOutcomeEvaluator | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.execution_engine = execution_engine or PlanGraphExecutionEngine(telemetry=telemetry)
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.context_builder = context_builder
        self.memory_store = memory_store
        self.evaluator = evaluator or DeterministicOutcomeEvaluator()
        self.telemetry = telemetry

        self._active_controllers: set[str] = set()
        self._lock = asyncio.Lock()

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        exec_id: str,
        session_id: str,
        iteration: int = 0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"loop-evt-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                execution_id=exec_id,
                attributes={"session_id": session_id, "iteration": iteration, **(attributes or {})},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def run(
        self,
        request: AgentRequest,
        config: AgentLoopConfig,
        tool_port: IToolPort,
    ) -> AgentLoopResult:
        """Run the Planning -> Execution -> Observation loop under explicit iteration ceilings and state machine bounds."""
        t0 = time.perf_counter()
        exec_id = f"loop-exec-{int(time.time() * 1000)}"

        # Active Controller Ownership (P3-4-INV-12)
        async with self._lock:
            if exec_id in self._active_controllers:
                raise ValueError(f"Execution '{exec_id}' is already owned by an active AgentLoop controller")
            self._active_controllers.add(exec_id)

        try:
            return await self._execute_loop(exec_id, request, config, tool_port, t0)
        finally:
            async with self._lock:
                self._active_controllers.discard(exec_id)

    async def _execute_loop(
        self,
        exec_id: str,
        request: AgentRequest,
        config: AgentLoopConfig,
        tool_port: IToolPort,
        t0: float,
    ) -> AgentLoopResult:
        state = AgentLoopState.INITIALIZING
        iteration = 0
        replan_count = 0
        observations: list[Observation] = []
        seen_fingerprints: set[str] = set()

        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_STARTED, exec_id, request.session_id, iteration)

        final_output = ""

        while state not in TERMINAL_LOOP_STATES:
            iteration += 1

            # P3-4-INV-01: max_iterations ceiling enforcement
            if iteration > config.max_iterations:
                state = AgentLoopState.FAILED
                final_output = f"Loop terminated: max_iterations limit ({config.max_iterations}) reached"
                break

            # 1. PLANNING STAGE
            state = AgentLoopState.PLANNING
            await self._safe_telemetry_event(RuntimeEventType.PLANNING_STARTED, exec_id, request.session_id, iteration)

            context_text = ""
            if self.context_builder:
                try:
                    context_text, _ = await self.context_builder.build_context(
                        session_id=request.session_id,
                        query_text=request.user_prompt,
                        max_tokens=4096,
                    )
                except Exception:
                    pass

            combined_prompt = f"{context_text}\nUser Query: {request.user_prompt}".strip()
            goal = AgentGoal(description=combined_prompt)
            ctx = PlanningContext(
                goal_component=PlanningGoal(goal=goal),
                resources_component=PlanningResources(),
            )

            # Generate PlanGraph
            plan_graph, planner_trace = self.execution_engine.planner.plan(ctx, session_id=request.session_id)
            fingerprint = compute_plan_fingerprint(plan_graph)

            # P3-4-INV-07: Infinite Loop Protection via Plan Fingerprinting
            if fingerprint in seen_fingerprints:
                state = AgentLoopState.FAILED
                final_output = "Loop terminated: repeated plan graph fingerprint generated without progress"
                break
            seen_fingerprints.add(fingerprint)

            # 2. PLAN VALIDATION STAGE (P3-4-INV-02 & P3-4-INV-03)
            state = AgentLoopState.PLAN_VALIDATION
            if config.require_plan_validation and self.tool_registry:
                for node_id, node in plan_graph.nodes.items():
                    try:
                        await self.tool_registry.validate_tool(node.step.tool_name)
                    except Exception as err:
                        if config.allow_replanning and replan_count < config.max_replans:
                            replan_count += 1
                            state = AgentLoopState.REPLANNING
                            continue
                        else:
                            state = AgentLoopState.FAILED
                            final_output = f"Plan validation failed for tool '{node.step.tool_name}': {err}"
                            break

            if state == AgentLoopState.FAILED:
                break

            # 3. EXECUTING STAGE
            state = AgentLoopState.READY_FOR_EXECUTION
            state = AgentLoopState.EXECUTING
            await self._safe_telemetry_event(RuntimeEventType.EXECUTION_STARTED, exec_id, request.session_id, iteration)

            rec_graph, results, trace = await self.execution_engine.execute_plan(
                ctx=ctx,
                tool_port=tool_port,
                execution_id=f"{exec_id}-iter-{iteration}",
                session_id=request.session_id,
            )

            # 4. OBSERVING STAGE
            state = AgentLoopState.OBSERVING
            success_cnt = sum(1 for r in results if r.success)
            fail_cnt = sum(1 for r in results if not r.success)
            pending_cnt = sum(1 for n in rec_graph.nodes.values() if n.step.status.value == "PENDING")

            obs = Observation(
                execution_id=exec_id,
                iteration=iteration,
                node_results=tuple(results),
                successful_nodes=success_cnt,
                failed_nodes=fail_cnt,
                pending_nodes=pending_cnt,
                terminal=fail_cnt == 0,
                summary=f"Iteration {iteration}: {success_cnt} succeeded, {fail_cnt} failed",
            )
            observations.append(obs)

            # 5. EVALUATING STAGE
            state = AgentLoopState.EVALUATING
            decision = await self.evaluator.evaluate(request, obs, config, iteration, replan_count)

            if decision.action == "COMPLETED":
                state = AgentLoopState.COMPLETED
                outputs = [r.output for r in results if r.success and r.output]
                final_output = "\n".join(outputs) if outputs else "Agent loop completed successfully"
            elif decision.action == "REPLAN":
                # P3-4-INV-02: max_replans ceiling enforcement
                if config.allow_replanning and replan_count < config.max_replans:
                    replan_count += 1
                    state = AgentLoopState.REPLANNING
                else:
                    state = AgentLoopState.FAILED
                    final_output = f"Loop failed: max_replans limit ({config.max_replans}) reached"
            else:
                state = AgentLoopState.FAILED
                final_output = f"Loop failed: {decision.reason}"

        # Terminal state persistence & telemetry
        dur_ms = (time.perf_counter() - t0) * 1000.0
        if self.memory_store:
            try:
                prov = MemoryProvenance(source_type="agent_loop", source_id=exec_id, confidence=1.0)
                mem = MemoryEntry(
                    memory_id=f"mem-loop-{exec_id}",
                    session_id=request.session_id,
                    execution_id=exec_id,
                    memory_type=MemoryType.EPISODIC,
                    content=f"Loop prompt '{request.user_prompt}' ended in {state.value}: {final_output}",
                    provenance=prov,
                )
                await self.memory_store.store(mem)
            except Exception:
                pass

        await self._safe_telemetry_event(
            RuntimeEventType.EXECUTION_COMPLETED if state == AgentLoopState.COMPLETED else RuntimeEventType.EXECUTION_FAILED,
            exec_id,
            request.session_id,
            iteration,
            attributes={"final_state": state.value, "dur_ms": dur_ms},
        )

        return AgentLoopResult(
            execution_id=exec_id,
            final_state=state,
            iterations=iteration,
            replans=replan_count,
            observations=tuple(observations),
            final_output=final_output,
            duration_ms=dur_ms,
        )

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an active agent loop execution task."""
        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_CANCELLED, execution_id, "unknown")
        return True
