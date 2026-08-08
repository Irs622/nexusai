"""LoopExecutor driving multi-turn agent execution loops for NexusAI Agent Runtime."""

from __future__ import annotations

from typing import Callable

from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import LoopDecision, StepStatus
from nexusai.brain.observation import ObservationMapper
from nexusai.brain.pipeline.pipeline import ExecutionPipeline
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionRequest
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.state_machine import AgentState
from nexusai.brain.strategy import IDecisionStrategy, IPlanningStrategy, IReflectionStrategy
from nexusai.domain.models import Observation
from nexusai.logging.logger import logger


class LoopExecutor:
    """Multi-turn loop executor orchestrating state machine transitions and pipeline stage runs.

    Follows execution loop:
    Planning -> Reasoning -> Tool -> Observation -> Compaction -> Reflection -> Decision.
    """

    def __init__(
        self,
        deps: RuntimeDependencies | None = None,
        planning_strategy: IPlanningStrategy | None = None,
        reflection_strategy: IReflectionStrategy | None = None,
        decision_strategy: IDecisionStrategy | None = None,
        tool_port: IToolPort | None = None,
        observation_mapper: ObservationMapper | None = None,
        pipeline: ExecutionPipeline | None = None,
    ) -> None:
        self.deps = deps or RuntimeDependencies(
            planning_strategy=planning_strategy or RuntimeDependencies().planning_strategy,
            reflection_strategy=reflection_strategy or RuntimeDependencies().reflection_strategy,
            decision_strategy=decision_strategy or RuntimeDependencies().decision_strategy,
        )
        self._planner = self.deps.planning_strategy
        self._reflection_strategy = self.deps.reflection_strategy
        self._decision_strategy = self.deps.decision_strategy
        self._tool_port = tool_port
        self._obs_mapper = observation_mapper or ObservationMapper()
        self._pipeline = pipeline or ExecutionPipeline()

        self.hooks: dict[str, list[Callable[[AgentRuntimeContext], None]]] = {
            "before_plan": [],
            "after_plan": [],
            "before_tool": [],
            "after_tool": [],
            "before_compaction": [],
            "after_compaction": [],
            "before_reflection": [],
            "after_turn": [],
        }

    def register_hook(
        self, event_name: str, callback: Callable[[AgentRuntimeContext], None]
    ) -> None:
        """Register a lifecycle hook callback."""
        if event_name in self.hooks:
            self.hooks[event_name].append(callback)

    def _trigger_hook(self, event_name: str, ctx: AgentRuntimeContext) -> None:
        """Trigger registered callbacks for a lifecycle event."""
        for cb in self.hooks.get(event_name, []):
            try:
                cb(ctx)
            except Exception as exc:
                logger.error(f"[LoopExecutor] Error in hook callback '{event_name}': {exc}")

    async def execute_loop(self, ctx: AgentRuntimeContext) -> WorkingMemory:
        """Execute multi-turn agent loop for given AgentRuntimeContext."""
        sm = ctx.state_machine
        mem = ctx.working_memory
        logger.info(
            f"[LoopExecutor] Starting multi-turn agent loop for goal '{mem.goal.description}'"
        )

        # 1. PLANNING
        self._trigger_hook("before_plan", ctx)
        sm.transition_to(AgentState.PLANNING)
        steps = await self.deps.planning_strategy.generate_plan(mem.goal, ctx)
        mem.steps = steps
        mem.current_step_index = 0
        if steps:
            steps[0].status = StepStatus.RUNNING

        self._trigger_hook("after_plan", ctx)
        sm.transition_to(AgentState.REASONING)

        max_iterations = 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            current_step = mem.current_step

            if current_step is None:
                logger.info("[LoopExecutor] No remaining active step. Goal processing completed.")
                sm.transition_to(AgentState.FINISHED)
                break

            logger.debug(
                f"[LoopExecutor] Iteration {iteration}: Processing step {current_step.step_id} - '{current_step.title}'"
            )

            latest_obs: Observation | None = None

            # 2. TOOL EXECUTION & OBSERVATION
            if current_step.tool_name and self._tool_port is not None:
                self._trigger_hook("before_tool", ctx)
                sm.transition_to(AgentState.TOOL_EXECUTION)

                request = ToolExecutionRequest(
                    tool_name=current_step.tool_name,
                    arguments=current_step.arguments,
                )
                tool_res = await self._tool_port.execute(request)

                sm.transition_to(AgentState.OBSERVING)
                latest_obs = self._obs_mapper.map_tool_result(tool_res)
                mem.record_observation(latest_obs)

                if not tool_res.success:
                    mem.record_failure(
                        step_id=current_step.step_id,
                        error_message=tool_res.error_message or "Tool execution error",
                    )
                self._trigger_hook("after_tool", ctx)
            else:
                latest_obs = Observation(
                    source="system",
                    tool_name=current_step.tool_name or "internal_step",
                    success=True,
                    payload=f"Executed step {current_step.step_id}: {current_step.title}",
                )
                mem.record_observation(latest_obs)

            # 3. CONTEXT COMPACTION (Pure state application of delta)
            self._trigger_hook("before_compaction", ctx)
            compaction_result = self.deps.compaction_pipeline.execute(
                memory=mem,
                budget=self.deps.context_budget,
                policy=self.deps.retention_policy,
            )
            mem.apply_compaction(compaction_result)
            self._trigger_hook("after_compaction", ctx)

            # Run single turn pass through passive ExecutionPipeline
            await self._pipeline.process(ctx.execution_context)
            self._trigger_hook("after_turn", ctx)

            # 4. REFLECTION
            self._trigger_hook("before_reflection", ctx)
            if sm.current_state not in (AgentState.REFLECTING, AgentState.FAILED):
                if sm.can_transition_to(AgentState.REFLECTING):
                    sm.transition_to(AgentState.REFLECTING)

            analysis = await self.deps.reflection_strategy.reflect(mem, latest_obs)

            # 5. DECISION
            if sm.can_transition_to(AgentState.DECISION):
                sm.transition_to(AgentState.DECISION)

            decision = self.deps.decision_strategy.decide(mem, analysis)
            logger.info(f"[LoopExecutor] Iteration {iteration} decision: {decision.value}")

            if decision == LoopDecision.COMPLETE:
                current_step.status = StepStatus.COMPLETED
                sm.transition_to(AgentState.FINISHED)
                break
            elif decision == LoopDecision.FAIL:
                current_step.status = StepStatus.FAILED
                sm.transition_to(AgentState.FAILED)
                break
            elif decision == LoopDecision.REPLAN:
                sm.transition_to(AgentState.REPLANNING)
                sm.transition_to(AgentState.PLANNING)
                replan_steps = await self.deps.planning_strategy.generate_plan(mem.goal, ctx)
                mem.steps = replan_steps
                mem.current_step_index = 0
                if replan_steps:
                    replan_steps[0].status = StepStatus.RUNNING
                sm.transition_to(AgentState.REASONING)
            elif decision == LoopDecision.CONTINUE:
                mem.advance_step()
                if sm.can_transition_to(AgentState.REASONING):
                    sm.transition_to(AgentState.REASONING)

        return mem
