"""Provider Session representation for stateful AI operations and agent context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from nexusai.core.annotations import stable


@stable
@dataclass
class ProviderSession:
    """Stateful container holding conversation state, tool memory, and session context."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str | None = None
    tool_state: dict[str, Any] = field(default_factory=dict)
    temporary_memory: dict[str, Any] = field(default_factory=dict)
    context_cache: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_tool_state(self, key: str, value: Any) -> None:
        """Update tool state entry."""
        self.tool_state[key] = value

    def get_tool_state(self, key: str, default: Any = None) -> Any:
        """Retrieve tool state entry."""
        return self.tool_state.get(key, default)
