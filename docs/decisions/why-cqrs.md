---
status: stable
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - core-architecture
review_cycle: yearly
last_reviewed: 2026-08-03
---

# Why CQRS (Command Query Responsibility Segregation)?

## Decision Rationale
1. **Security Isolation**: Read-only Queries are safe and auto-approved, while state-modifying Commands route through permission guards.
2. **Audit Logging**: Every command dispatches events to `EventBus` for complete execution transparency.
