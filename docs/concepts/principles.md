---
status: stable
audience:
  - contributors
  - maintainers
owner:
  - core-team
applies_to:
  - engineering-standards
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🏗️ Engineering Principles

These engineering tenets guide all code contributions, architecture decisions, and code reviews in **NexusAI**.

---

## 🏛️ Core Tenets

### 1. 🔄 Dependency Inversion (Interface First)
High-level modules (Brain, Workflow) must never depend on low-level modules (specific OpenAI API SDK, SQLite driver). Both must depend on abstractions (`BaseModelProvider`, `BaseMemory`, `BaseTool`).

### 2. ⚡ Async-First Architecture
All IO-bound operations (API calls, file access, SQLite queries, network requests) must be `async`. Never block the asyncio main looper with synchronous sleep or blocking HTTP requests.

### 3. 🧩 Composition Over Inheritance
Avoid deep class inheritance hierarchies. Use small, focused classes composed together (e.g. `BrainCoordinator` takes a `model_provider`, `registry`, `command_bus`, `memory`).

### 4. 🔀 Event-Driven Decoupling
Components publish events (`EventBus`) rather than calling other subsystems directly. This allows plugins and monitoring adapters to hook into system actions without altering core logic.

### 5. 🛡️ Defense-in-Depth & Explicit Validation
All external inputs (user prompts, API responses, tool arguments) must be parsed and validated using Pydantic schemas before reaching internal domain handlers.

### 6. 🧼 Clean Architecture & CQRS
Keep business logic pure and decoupled from framework details (FastAPI, Typer). Command execution flows strictly through command buses and tool registries.
