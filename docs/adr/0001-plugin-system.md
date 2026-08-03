---
status: accepted
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - plugin-system
review_cycle: yearly
last_reviewed: 2026-08-03
---

# ADR 0001: Extensible Tool Plugin Architecture

## Context
NexusAI requires a modular mechanism for extending agent capabilities without bloating the core runtime codebase.

## Decision
We adopt a lightweight `BaseTool` & `BasePlugin` inheritance contract with a centralized `ToolRegistry` container.

## Consequences
- **Positive**: Third-party tool extensions can be created in < 50 LOC.
- **Negative**: Requires strict parameter validation via Pydantic to ensure security safety.
