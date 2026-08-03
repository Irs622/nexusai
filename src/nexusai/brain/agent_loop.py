"""10-State Autonomous Agent Loop with Lifecycle Hooks for NexusAI."""
import uuid
from typing import Callable, Dict, List, Optional
from nexusai.domain.models import (
    AgentState, Goal, AgentContext, AgentSession, BudgetDecision, GoalCompletionStatus, Observation
)
from nexusai.brain.reasoning import ReasoningEngine
from nexusai.brain.compiler import WorkflowCompiler
from nexusai.brain.budget import ResourceBudgetEngine
from nexusai.brain.observation import ToolObserver

class AutonomousAgentLoop:
    """Orchestrates 10-state lifecycle: IDLE -> PLANNING -> EXECUTING -> OBSERVING -> EVALUATING -> REPLANNING -> WAITING -> FINISHED (FAILED/CANCELLED)."""

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEngine] = None,
        compiler: Optional[WorkflowCompiler] = None,
        budget_engine: Optional[ResourceBudgetEngine] = None,
    ) -> None:
        self.reasoning_engine = reasoning_engine or ReasoningEngine()
        self.compiler = compiler or WorkflowCompiler()
        self.budget_engine = budget_engine or ResourceBudgetEngine()
        self.observer = ToolObserver()
        
        # Lifecycle Hooks
        self.hooks: Dict[str, List[Callable[[AgentContext], None]]] = {
            "before_plan": [],
            "after_plan": [],
            "before_tool": [],
            "after_tool": [],
            "before_finish": [],
        }

    def register_hook(self, event_name: str, callback: Callable[[AgentContext], None]) -> None:
        """Register a lifecycle hook callback."""
        if event_name in self.hooks:
            self.hooks[event_name].append(callback)

    def _trigger_hook(self, event_name: str, context: AgentContext) -> None:
        """Trigger registered callbacks for a lifecycle event."""
        for cb in self.hooks.get(event_name, []):
            cb(context)

    async def run_session(self, session: AgentSession, goal: Goal) -> AgentContext:
        """Execute full 10-state autonomous loop for an AgentSession."""
        context = AgentContext(goal=goal, session_id=session.session_id, current_state=AgentState.IDLE)

        # 1. PLANNING
        self._trigger_hook("before_plan", context)
        context = context.update(current_state=AgentState.PLANNING)
        goal_plan = await self.reasoning_engine.generate_plan(goal)
        exec_plan = self.compiler.compile(goal_plan)
        context = context.update(plan=exec_plan)
        self._trigger_hook("after_plan", context)

        # 2. EXECUTING & OBSERVING & EVALUATING LOOP
        context = context.update(current_state=AgentState.EXECUTING)
        
        for step in exec_plan.execution_steps:
            # Check Budget
            decision = self.budget_engine.evaluate_budget(context)
            if decision == BudgetDecision.STOP:
                context = context.update(current_state=AgentState.FAILED)
                return context
            elif decision == BudgetDecision.WAIT or decision == BudgetDecision.ASK_USER:
                context = context.update(current_state=AgentState.WAITING)
                return context

            self._trigger_hook("before_tool", context)
            
            # Execute & Observe
            obs = self.observer.create_observation(
                tool_name=step.get("capabilities", ["workspace"])[0],
                output_payload=f"Executed step: {step['title']}",
                success=True,
            )
            session.history.append(obs)
            
            # Update Context Metrics
            context = context.update(
                tool_calls_count=context.tool_calls_count + 1,
                current_state=AgentState.OBSERVING,
            )
            self._trigger_hook("after_tool", context)

            # Evaluate
            context = context.update(current_state=AgentState.EVALUATING)
            eval_res = self.reasoning_engine.evaluate_observation(obs)
            
            if eval_res.goal_status == GoalCompletionStatus.PARTIAL and eval_res.retry_recommended:
                context = context.update(
                    current_state=AgentState.REPLANNING,
                    retries_count=context.retries_count + 1,
                )

        # FINISHED
        self._trigger_hook("before_finish", context)
        context = context.update(current_state=AgentState.FINISHED)
        return context
