"""Agent Collaboration Mesh managing asynchronous message routing and mailboxes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nexusai.brain.domain.collaboration import A2AMessage
from nexusai.logging.logger import logger

if TYPE_CHECKING:
    from nexusai.brain.runtime.collaboration.specialists import BaseSpecializedAgent


class AgentCollaborationMesh:
    """Central message routing bus providing mailboxes and history tracking for specialized agents."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseSpecializedAgent] = {}
        self._mailboxes: dict[str, asyncio.Queue[A2AMessage]] = {}
        self._conversation_history: dict[str, list[A2AMessage]] = {}
        self._lock = asyncio.Lock()

    @property
    def total_registered_agents(self) -> int:
        """Return total agents registered in the collaboration mesh."""
        return len(self._agents)

    def register_agent(self, agent: BaseSpecializedAgent) -> None:
        """Register an agent into the mesh and allocate its incoming mailbox."""
        self._agents[agent.agent_id] = agent
        self._mailboxes[agent.agent_id] = asyncio.Queue()
        agent.attach_mesh(self)
        logger.debug(f"[A2AMesh] Registered agent '{agent.agent_id}' ({agent.role.value})")

    def deregister_agent(self, agent_id: str) -> None:
        """Deregister an agent and remove its mailbox."""
        self._agents.pop(agent_id, None)
        self._mailboxes.pop(agent_id, None)
        logger.debug(f"[A2AMesh] Deregistered agent '{agent_id}'")

    def get_agent(self, agent_id: str) -> BaseSpecializedAgent | None:
        """Retrieve registered agent by ID."""
        return self._agents.get(agent_id)

    async def send_message(self, message: A2AMessage) -> bool:
        """Deliver message to recipient mailbox, or broadcast to all agents if recipient_id is '*'."""
        async with self._lock:
            # Record in conversation history
            self._conversation_history.setdefault(message.conversation_id, []).append(message)

        if message.is_broadcast():
            # Broadcast to all agents except sender
            delivered_any = False
            for aid, q in self._mailboxes.items():
                if aid != message.sender_id:
                    await q.put(message)
                    delivered_any = True
            return delivered_any

        # Targeted point-to-point delivery
        target_mailbox = self._mailboxes.get(message.recipient_id)
        if target_mailbox is not None:
            await target_mailbox.put(message)
            return True

        logger.warning(
            f"[A2AMesh] Message {message.message_id} dropped: recipient '{message.recipient_id}' not found"
        )
        return False

    async def receive_message(self, agent_id: str, timeout: float | None = None) -> A2AMessage | None:
        """Fetch the next incoming message from an agent's mailbox."""
        mailbox = self._mailboxes.get(agent_id)
        if mailbox is None:
            return None

        try:
            if timeout is not None:
                return await asyncio.wait_for(mailbox.get(), timeout=timeout)
            return await mailbox.get()
        except (asyncio.TimeoutError, TimeoutError):
            return None

    def get_history(self, conversation_id: str) -> tuple[A2AMessage, ...]:
        """Return full chronological message history for a conversation."""
        return tuple(self._conversation_history.get(conversation_id, []))
