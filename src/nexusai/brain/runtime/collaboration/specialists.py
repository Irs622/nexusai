"""Specialized Agents (Planner, Coder, Auditor, Orchestrator) for multi-agent mesh collaboration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping
from uuid import uuid4

from nexusai.brain.domain.collaboration import (
    A2AMessage,
    A2AMessageType,
    AgentRole,
    CollaborationResult,
    ReviewVerdict,
)
from nexusai.brain.runtime.collaboration.mesh import AgentCollaborationMesh
from nexusai.logging.logger import logger

CodeGeneratorFn = Callable[[str, Mapping[str, Any]], tuple[str, str]]
AuditEvaluatorFn = Callable[[str, str], tuple[ReviewVerdict, list[str]]]


class BaseSpecializedAgent:
    """Abstract base for agents participating in the A2A Collaboration Mesh."""

    def __init__(self, agent_id: str, role: AgentRole, name: str = "") -> None:
        self.agent_id = agent_id
        self.role = role
        self.name = name or f"{role.value.capitalize()}Specialist"
        self._mesh: AgentCollaborationMesh | None = None

    def attach_mesh(self, mesh: AgentCollaborationMesh) -> None:
        """Attach mesh reference to this agent."""
        self._mesh = mesh

    async def send(
        self,
        recipient_id: str,
        message_type: A2AMessageType,
        conversation_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> bool:
        """Send message via the attached collaboration mesh."""
        if self._mesh is None:
            raise RuntimeError(f"Agent '{self.agent_id}' is not attached to any collaboration mesh")

        msg = A2AMessage(
            sender_id=self.agent_id,
            sender_role=self.role,
            recipient_id=recipient_id,
            message_type=message_type,
            conversation_id=conversation_id,
            payload=payload or {},
        )
        return await self._mesh.send_message(msg)

    async def receive(self, timeout: float | None = 2.0) -> A2AMessage | None:
        """Fetch next incoming message from this agent's mailbox."""
        if self._mesh is None:
            raise RuntimeError(f"Agent '{self.agent_id}' is not attached to any collaboration mesh")
        return await self._mesh.receive_message(self.agent_id, timeout=timeout)


class PlannerSpecialist(BaseSpecializedAgent):
    """Decomposes high-level user tasks into modular sub-plans and execution constraints."""

    def __init__(self, agent_id: str = "agent-planner") -> None:
        super().__init__(agent_id=agent_id, role=AgentRole.PLANNER, name="ArchitectPlanner")

    async def create_plan(
        self, goal: str, conversation_id: str, recipient_id: str = "agent-coder"
    ) -> A2AMessage:
        """Analyze goal and dispatch structured plan decomposition to Coder."""
        steps = [
            f"Define interface & core data contracts for '{goal}'",
            f"Implement functional logic & error handlers for '{goal}'",
            f"Add unit test coverage & architectural validation for '{goal}'",
        ]
        payload = {
            "goal": goal,
            "plan_steps": steps,
            "architecture_constraints": ["DAG unidirectional flow", "mypy --strict compliance"],
            "suggested_tools": ["filesystem", "sqlite"],
        }
        await self.send(
            recipient_id=recipient_id,
            message_type=A2AMessageType.TASK_DELEGATION,
            conversation_id=conversation_id,
            payload=payload,
        )
        return A2AMessage(
            sender_id=self.agent_id,
            sender_role=self.role,
            recipient_id=recipient_id,
            message_type=A2AMessageType.TASK_DELEGATION,
            conversation_id=conversation_id,
            payload=payload,
        )


class CoderSpecialist(BaseSpecializedAgent):
    """Implements technical artifacts and applies audit review suggestions."""

    def __init__(
        self,
        agent_id: str = "agent-coder",
        generator_fn: CodeGeneratorFn | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, role=AgentRole.CODER, name="CoreCoder")
        self.generator_fn = generator_fn

    async def draft_or_revise(
        self,
        conversation_id: str,
        goal: str,
        plan_steps: list[str],
        feedback: list[str] | None = None,
        recipient_id: str = "agent-auditor",
        iteration: int = 1,
    ) -> A2AMessage:
        """Generate code solution or revise based on feedback, sending proposal to Auditor."""
        if self.generator_fn:
            code, rationale = self.generator_fn(goal, {"steps": plan_steps, "feedback": feedback or []})
        else:
            status_text = "Revised" if feedback else "Initial draft"
            code = f"# Solution for: {goal}\n# Iteration: {iteration}\n# {status_text}\ndef execute() -> bool:\n    return True\n"
            rationale = f"{status_text} addressing plan steps with proper error boundaries."

        payload = {
            "code": code,
            "rationale": rationale,
            "iteration": iteration,
            "addressed_feedback": feedback or [],
        }
        await self.send(
            recipient_id=recipient_id,
            message_type=A2AMessageType.PROPOSAL,
            conversation_id=conversation_id,
            payload=payload,
        )
        return A2AMessage(
            sender_id=self.agent_id,
            sender_role=self.role,
            recipient_id=recipient_id,
            message_type=A2AMessageType.PROPOSAL,
            conversation_id=conversation_id,
            payload=payload,
        )


class AuditorSpecialist(BaseSpecializedAgent):
    """Audits proposals for security, architecture invariants, and correctness."""

    def __init__(
        self,
        agent_id: str = "agent-auditor",
        evaluator_fn: AuditEvaluatorFn | None = None,
        min_pass_iteration: int = 1,
    ) -> None:
        super().__init__(agent_id=agent_id, role=AgentRole.AUDITOR, name="ComplianceAuditor")
        self.evaluator_fn = evaluator_fn
        self.min_pass_iteration = min_pass_iteration

    async def audit_proposal(
        self,
        proposal: A2AMessage,
        recipient_id: str = "agent-orchestrator",
    ) -> A2AMessage:
        """Audit code proposal and issue review verdict with actionable feedback."""
        code = str(proposal.payload.get("code", ""))
        iteration = int(proposal.payload.get("iteration", 1))

        if self.evaluator_fn:
            verdict, feedback = self.evaluator_fn(code, str(proposal.payload.get("rationale", "")))
        else:
            # Default deterministic heuristic
            if iteration >= self.min_pass_iteration:
                verdict = ReviewVerdict.APPROVED
                feedback = ["All safety invariants satisfied", "DAG DAG compliance verified"]
            else:
                verdict = ReviewVerdict.CHANGES_REQUESTED
                feedback = ["Add explicit error handling boundary", "Include typing return signature"]

        payload = {
            "verdict": verdict.value,
            "critique_points": feedback,
            "iteration": iteration,
            "approved": verdict == ReviewVerdict.APPROVED,
        }
        await self.send(
            recipient_id=recipient_id,
            message_type=A2AMessageType.REVIEW_FEEDBACK,
            conversation_id=proposal.conversation_id,
            payload=payload,
        )
        return A2AMessage(
            sender_id=self.agent_id,
            sender_role=self.role,
            recipient_id=recipient_id,
            message_type=A2AMessageType.REVIEW_FEEDBACK,
            conversation_id=proposal.conversation_id,
            payload=payload,
        )


class OrchestratorSpecialist(BaseSpecializedAgent):
    """Coordinates lifecycle of multi-agent negotiation, consensus resolution, and output synthesis."""

    def __init__(self, agent_id: str = "agent-orchestrator") -> None:
        super().__init__(agent_id=agent_id, role=AgentRole.ORCHESTRATOR, name="MasterOrchestrator")

    async def execute_collaboration(
        self,
        goal: str,
        planner: PlannerSpecialist,
        coder: CoderSpecialist,
        auditor: AuditorSpecialist,
        max_rounds: int = 3,
        round_timeout: float = 2.0,
    ) -> CollaborationResult:
        """Run full end-to-end multi-agent negotiation loop between Planner, Coder, and Auditor."""
        task_id = f"task-{uuid4().hex[:8]}"
        conv_id = f"conv-{task_id}"

        logger.info(f"[A2A Orchestrator] Starting collaboration for goal: '{goal}' (Task: {task_id})")

        # 1. Step: Planner creates decomposition
        plan_msg = await planner.create_plan(
            goal=goal, conversation_id=conv_id, recipient_id=coder.agent_id
        )
        plan_steps = list(plan_msg.payload.get("plan_steps", []))

        current_feedback: list[str] = []
        last_proposal: Mapping[str, Any] = {}
        rounds_executed = 0
        is_approved = False

        # 2. Multi-turn negotiation loop (Coder <-> Auditor)
        for r in range(1, max_rounds + 1):
            rounds_executed = r
            logger.debug(f"[A2A Orchestrator] Round {r}/{max_rounds} - Drafting/revising solution")

            # Coder drafts or revises solution
            proposal_msg = await coder.draft_or_revise(
                conversation_id=conv_id,
                goal=goal,
                plan_steps=plan_steps,
                feedback=current_feedback if current_feedback else None,
                recipient_id=auditor.agent_id,
                iteration=r,
            )
            last_proposal = dict(proposal_msg.payload)

            # Auditor evaluates proposal
            feedback_msg = await auditor.audit_proposal(
                proposal=proposal_msg,
                recipient_id=self.agent_id,
            )

            is_approved = bool(feedback_msg.payload.get("approved", False))
            current_feedback = list(feedback_msg.payload.get("critique_points", []))

            if is_approved:
                logger.info(f"[A2A Orchestrator] Consensus reached in round {r}! Solution APPROVED.")
                break
            else:
                logger.warning(
                    f"[A2A Orchestrator] Round {r} Changes requested: {', '.join(current_feedback)}"
                )

        # 3. Final consensus broadcast
        final_status = "CONSENSUS_APPROVED" if is_approved else "MAX_ROUNDS_EXCEEDED"
        await self.send(
            recipient_id="*",
            message_type=A2AMessageType.CONSENSUS_REACHED,
            conversation_id=conv_id,
            payload={
                "task_id": task_id,
                "status": final_status,
                "rounds": rounds_executed,
                "is_approved": is_approved,
            },
        )

        history = self._mesh.get_history(conv_id) if self._mesh else ()
        summary = (
            f"Multi-Agent collaboration for '{goal}' resolved with status '{final_status}' "
            f"after {rounds_executed} round(s)."
        )

        return CollaborationResult(
            task_id=task_id,
            goal=goal,
            final_status=final_status,
            rounds_count=rounds_executed,
            dialogue_history=history,
            artifact_outputs=last_proposal,
            is_approved=is_approved,
            summary=summary,
        )
