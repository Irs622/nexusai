---
status: stable
audience:
  - maintainers
  - contributors
owner:
  - core-team
applies_to:
  - observability
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔭 Observability Framework

NexusAI uses a multi-tier observability pipeline:

1. **Structured Logging**: `Loguru` logger outputs formatted logs to `logs/nexusai.log`.
2. **Audit Sink**: Security events and tool executions append to `logs/audit.log`.
3. **Event Stream**: `EventBus` broadcasts runtime events (`ToolExecutedEvent`, `SecurityAlertEvent`) to UI & dashboard subscribers.
