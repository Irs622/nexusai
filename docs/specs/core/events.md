---
status: stable
audience:
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - event-bus
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 📡 Event Bus Specification

## 1. Overview

The `EventBus` provides asynchronous, decoupled message passing across subsystems.

---

## 2. Core System Events

| Event Class | Emitted When | Payload Attributes |
| :--- | :--- | :--- |
| `ToolExecutedEvent` | A tool finishes execution | `tool_name: str`, `arguments: dict`, `result: str`, `duration_ms: float` |
| `MemoryUpdatedEvent` | Conversation turn or fact is saved | `session_id: str`, `role: str`, `content: str` |
| `SecurityAlertEvent` | A dangerous command is blocked | `command: str`, `risk_level: str`, `reason: str` |
| `WorkflowStartedEvent` | Agent workflow graph begins prompt | `prompt: str`, `session_id: str` |
| `WorkflowFinishedEvent` | Agent workflow finishes synthesis | `final_response: str`, `turn_count: int` |
