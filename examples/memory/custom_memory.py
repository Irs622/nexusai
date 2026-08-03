"""Example custom memory backend adapter for NexusAI."""
from typing import Any, Dict, List
from nexusai.memory.base import BaseMemory

class InMemoryAdapter(BaseMemory):
    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []

    async def initialize_db(self) -> None:
        pass

    async def save_turn(self, session_id: str, role: str, content: str) -> None:
        self.history.append({"session_id": session_id, "role": role, "content": content})

    async def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return [h for h in self.history if h["session_id"] == session_id][-limit:]

    async def clear_history(self, session_id: str) -> None:
        self.history = [h for h in self.history if h["session_id"] != session_id]
