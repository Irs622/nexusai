"""AgentRuntimeContext composition container for NexusAI Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from nexusai.brain.runtime.context import ExecutionContext
from nexusai.brain.runtime.working_memory import WorkingMemory
from nexusai.brain.state_machine import AgentStateMachine


@dataclass
class AgentRuntimeContext:
    """Composition root transport context for multi-turn agent sessions.

    Wraps stateless Brain ExecutionContext alongside Agent WorkingMemory and StateMachine.

    Attributes:
        execution_context: Stateless Brain Runtime ExecutionContext.
        working_memory: Ephemeral WorkingMemory container.
        state_machine: Pure AgentStateMachine validator.
    """

    execution_context: ExecutionContext
    working_memory: WorkingMemory
    state_machine: AgentStateMachine = field(default_factory=AgentStateMachine)
