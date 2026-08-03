---
status: stable
audience:
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - error-model
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🛑 Error Model Specification

## 1. Exception Hierarchy

All custom exceptions in NexusAI MUST inherit from `NexusAIError` in `nexusai.core.errors`:

```
NexusAIError (Base Exception)
├── ConfigurationError       # Malformed or missing settings / env vars
├── SecurityViolationError   # Command blocked by SecurityGuard
├── ModelProviderError       # LLM API failure or unparseable response
├── ToolExecutionError      # Tool execution runtime exception
└── MemoryError             # SQLite or vector database failure
```

---

## 2. Standard Exception Format

```python
class NexusAIError(Exception):
    """Base exception for all NexusAI errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
```
