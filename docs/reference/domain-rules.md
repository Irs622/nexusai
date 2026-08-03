---
status: stable
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - architecture-design
review_cycle: yearly
last_reviewed: 2026-08-03
---

# 📐 Clean Domain Architecture & Layer Rules

## 1. Directional Dependency Principle

Dependencies in NexusAI flow strictly inward toward core abstractions:

```
Interfaces (CLI / Web UI)
    ↓
Infrastructure (Adapters: OpenAI, SQLite, macOS System)
    ↓
Application (Services & CQRS Bus)
    ↓
Domain (Core Base Classes & Exceptions)
```

---

## 2. Forbidden Import Rules
1. **Domain (`nexusai.core`)** must NOT import Application, Infrastructure, or Interfaces.
2. **Infrastructure (`nexusai.models`, `nexusai.memory`)** must NOT import Interfaces (`cli`, `api`).
3. **Tools (`nexusai.tools`)** must NOT import UI components directly.
