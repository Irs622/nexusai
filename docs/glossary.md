---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - terminology
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 📖 System Glossary

| Term | Definition |
| :--- | :--- |
| **Brain** | The core LLM orchestration engine (`BrainCoordinator`) managing workflow loops. |
| **Provider** | Adapter interface (`BaseModelProvider`) wrapping an LLM vendor API (OpenAI, Ollama, etc.). |
| **Tool** | Self-contained executable capability (`BaseTool`) registered with `ToolRegistry`. |
| **Workflow** | Cyclic state graph orchestrating agent node transitions. |
| **Guard** | Security evaluator (`SecurityGuard`) enforcing risk classification & command sanitization. |
| **Bus** | Decoupled CQRS message dispatcher (`CommandBus`, `QueryBus`, `EventBus`). |
| **Context** | Workspace files and indexed knowledge retrieved via vector search. |
