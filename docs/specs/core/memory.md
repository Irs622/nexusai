---
status: stable
audience:
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - memory-subsystem
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🧠 Memory Subsystem Specification

## 1. Overview

The Memory Subsystem provides dual-tier local memory storage:
1. **Short-Term Conversational History**: Recent chat turns per session stored in SQLite.
2. **Long-Term Fact Store**: Episodic facts and workspace context indexed locally via ChromaDB vector embeddings.

---

## 2. Abstract Memory Interface (`BaseMemory`)

Every memory backend adapter MUST implement the `BaseMemory` abstract interface:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseMemory(ABC):
    @abstractmethod
    async def initialize_db(self) -> None:
        """Initialize database tables or vector collections."""
        pass

    @abstractmethod
    async def save_turn(self, session_id: str, role: str, content: str) -> None:
        """Save a single conversation turn."""
        pass

    @abstractmethod
    async def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent conversation history for a session."""
        pass

    @abstractmethod
    async def clear_history(self, session_id: str) -> None:
        """Clear history for a given session."""
        pass
```

---

## 3. SQLite Database Schema

Conversation turns are stored in SQLite table `conversation_turns`:

```sql
CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_timestamp 
ON conversation_turns (session_id, timestamp);
```
