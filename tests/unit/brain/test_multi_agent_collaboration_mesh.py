"""Unit tests for Multi-Agent Collaboration Mesh (A2A Protocol, Routing & Specialists)."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.collaboration import (
    A2AMessageType,
    AgentRole,
)
from nexusai.brain.runtime.collaboration.mesh import AgentCollaborationMesh
from nexusai.brain.runtime.collaboration.specialists import (
    AuditorSpecialist,
    BaseSpecializedAgent,
    CoderSpecialist,
    OrchestratorSpecialist,
    PlannerSpecialist,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a2a_message_creation_and_routing() -> None:
    """Verify point-to-point and broadcast message delivery through AgentCollaborationMesh."""
    mesh = AgentCollaborationMesh()

    agent_a = BaseSpecializedAgent("agent-a", AgentRole.PLANNER)
    agent_b = BaseSpecializedAgent("agent-b", AgentRole.CODER)
    agent_c = BaseSpecializedAgent("agent-c", AgentRole.AUDITOR)

    mesh.register_agent(agent_a)
    mesh.register_agent(agent_b)
    mesh.register_agent(agent_c)

    assert mesh.total_registered_agents == 3

    # 1. Point-to-point send
    sent = await agent_a.send(
        recipient_id="agent-b",
        message_type=A2AMessageType.TASK_DELEGATION,
        conversation_id="conv-100",
        payload={"task": "Implement module"},
    )
    assert sent is True

    # Agent B receives it
    msg_b = await agent_b.receive(timeout=0.5)
    assert msg_b is not None
    assert msg_b.sender_id == "agent-a"
    assert msg_b.message_type == A2AMessageType.TASK_DELEGATION
    assert msg_b.payload["task"] == "Implement module"

    # Agent C should have an empty mailbox
    msg_c = await agent_c.receive(timeout=0.1)
    assert msg_c is None

    # 2. Broadcast send
    sent_broadcast = await agent_a.send(
        recipient_id="*",
        message_type=A2AMessageType.BROADCAST,
        conversation_id="conv-100",
        payload={"announcement": "Cluster ready"},
    )
    assert sent_broadcast is True

    # Both B and C receive broadcast
    b_broadcast = await agent_b.receive(timeout=0.5)
    c_broadcast = await agent_c.receive(timeout=0.5)
    assert b_broadcast is not None and b_broadcast.payload["announcement"] == "Cluster ready"
    assert c_broadcast is not None and c_broadcast.payload["announcement"] == "Cluster ready"

    # Verify conversation history
    history = mesh.get_history("conv-100")
    assert len(history) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_collaboration_happy_path() -> None:
    """Verify end-to-end collaboration where proposal is approved on first iteration."""
    mesh = AgentCollaborationMesh()

    planner = PlannerSpecialist("planner-1")
    coder = CoderSpecialist("coder-1")
    auditor = AuditorSpecialist("auditor-1", min_pass_iteration=1)
    orchestrator = OrchestratorSpecialist("orchestrator-1")

    mesh.register_agent(planner)
    mesh.register_agent(coder)
    mesh.register_agent(auditor)
    mesh.register_agent(orchestrator)

    res = await orchestrator.execute_collaboration(
        goal="Build async memory eviction queue",
        planner=planner,
        coder=coder,
        auditor=auditor,
        max_rounds=3,
    )

    assert res.is_approved is True
    assert res.rounds_count == 1
    assert res.final_status == "CONSENSUS_APPROVED"
    assert len(res.dialogue_history) >= 4  # plan, proposal, feedback, consensus
    assert "execute" in res.artifact_outputs.get("code", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_collaboration_with_revisions() -> None:
    """Verify multi-round negotiation where auditor requests changes before approving."""
    mesh = AgentCollaborationMesh()

    planner = PlannerSpecialist("planner-2")
    coder = CoderSpecialist("coder-2")
    # Auditor requests changes on round 1, approves on round 2
    auditor = AuditorSpecialist("auditor-2", min_pass_iteration=2)
    orchestrator = OrchestratorSpecialist("orchestrator-2")

    mesh.register_agent(planner)
    mesh.register_agent(coder)
    mesh.register_agent(auditor)
    mesh.register_agent(orchestrator)

    res = await orchestrator.execute_collaboration(
        goal="Implement strict token validation guard",
        planner=planner,
        coder=coder,
        auditor=auditor,
        max_rounds=3,
    )

    assert res.is_approved is True
    assert res.rounds_count == 2
    assert res.final_status == "CONSENSUS_APPROVED"
    assert res.artifact_outputs.get("iteration") == 2
    assert len(res.artifact_outputs.get("addressed_feedback", [])) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_collaboration_max_rounds_cutoff() -> None:
    """Verify collaboration cutoff when max_rounds limit is reached without approval."""
    mesh = AgentCollaborationMesh()

    planner = PlannerSpecialist("planner-3")
    coder = CoderSpecialist("coder-3")
    # Auditor never approves (min_pass_iteration=99)
    auditor = AuditorSpecialist("auditor-3", min_pass_iteration=99)
    orchestrator = OrchestratorSpecialist("orchestrator-3")

    mesh.register_agent(planner)
    mesh.register_agent(coder)
    mesh.register_agent(auditor)
    mesh.register_agent(orchestrator)

    res = await orchestrator.execute_collaboration(
        goal="Solve unconstrained SAT problem",
        planner=planner,
        coder=coder,
        auditor=auditor,
        max_rounds=2,
    )

    assert res.is_approved is False
    assert res.rounds_count == 2
    assert res.final_status == "MAX_ROUNDS_EXCEEDED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unattached_agent_raises_runtime_error() -> None:
    """Verify unattached agent raises RuntimeError when attempting to send/receive."""
    free_agent = BaseSpecializedAgent("unattached", AgentRole.CODER)

    with pytest.raises(RuntimeError, match="not attached to any collaboration mesh"):
        await free_agent.send("agent-b", A2AMessageType.PROPOSAL, "conv-0")

    with pytest.raises(RuntimeError, match="not attached to any collaboration mesh"):
        await free_agent.receive()
