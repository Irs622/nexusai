"""PlanGraphExecutionEngine for executing PlanGraph DAG nodes according to dependency topology."""

from __future__ import annotations

import time

from nexusai.brain.domain.agent import (
    DecisionTrace,
    ExecutionFailure,
    FailureReason,
    PlanGraph,
    PlanningContext,
    StepStatus,
)
from nexusai.brain.planner.stages import ExecutionPlanner, RecoveryPlanner
from nexusai.brain.planner.validator import PlanValidator
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest, ToolExecutionResult
from nexusai.brain.runtime.execution_policy import CircuitBreaker, ExecutionPolicy


class PlanGraphExecutionEngine:
    """Step-by-step DAG execution engine running PlanGraph nodes enforcing ExecutionPolicy."""

    def __init__(
        self,
        planner: ExecutionPlanner | None = None,
        validator: PlanValidator | None = None,
        recovery_planner: RecoveryPlanner | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self.planner = planner or ExecutionPlanner()
        self.validator = validator or PlanValidator()
        self.recovery_planner = recovery_planner or RecoveryPlanner()
        self.policy = policy or ExecutionPolicy()
        self.circuit_breaker = CircuitBreaker()

    async def execute_plan(
        self,
        ctx: PlanningContext,
        tool_port: IToolPort,
        session_id: str = "session-1",
    ) -> tuple[PlanGraph, list[ToolExecutionResult], DecisionTrace]:
        """Execute PlanningContext through Planner, PlanValidator, and ToolPort."""

        # 1. Generate PlanGraph
        plan_graph, trace = self.planner.plan(ctx, session_id=session_id)

        # 2. Validate PlanGraph
        val_result = self.validator.validate(plan_graph, constraints=ctx.constraints_component)
        if not val_result.is_valid:
            raise RuntimeError(
                f"PlanGraph validation failed: {[i.message for i in val_result.issues]}"
            )

        # 3. Topological Execution of PlanGraph nodes
        results: list[ToolExecutionResult] = []
        executed_nodes: set[int] = set()

        for node_id in sorted(plan_graph.nodes.keys()):
            node = plan_graph.nodes[node_id]

            # Verify node dependencies completed
            for dep_id in node.dependencies:
                if dep_id not in executed_nodes:
                    raise RuntimeError(
                        f"Dependency step {dep_id} not executed before step {node_id}"
                    )

            step = node.step
            step.status = StepStatus.RUNNING

            if step.tool_name:
                self.circuit_breaker.check_execution_allowed()
                req = ToolExecutionRequest(
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                    execution_id=f"step-{step.step_id}",
                )

                t0 = time.perf_counter()
                try:
                    res = await tool_port.execute(req)
                    _duration_ms = (time.perf_counter() - t0) * 1000.0

                    if res.success:
                        step.status = StepStatus.COMPLETED
                        self.circuit_breaker.record_success()
                    else:
                        step.status = StepStatus.FAILED
                        self.circuit_breaker.record_failure()

                    results.append(res)
                except Exception as err:
                    step.status = StepStatus.FAILED
                    self.circuit_breaker.record_failure()
                    failure = ExecutionFailure(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        reason=FailureReason.TOOL_EXECUTION_ERROR,
                        error_message=str(err),
                    )
                    rec_strat, rec_step = self.recovery_planner.plan_recovery(failure)
                    results.append(
                        ToolExecutionResult(
                            request_id=f"step-{step.step_id}",
                            tool_name=step.tool_name,
                            success=False,
                            error_message=f"Execution error: {err} (Recovery Strategy: {rec_strat.value})",
                        )
                    )
            else:
                step.status = StepStatus.COMPLETED

            executed_nodes.add(node_id)

        return plan_graph, results, trace
