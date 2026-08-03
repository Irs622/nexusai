---
status: stable
audience:
  - contributors
  - architects
owner:
  - core-team
applies_to:
  - architecture-design
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 📐 System Design & Component Interactions

This document outlines how the primary subsystems of **NexusAI** interact during application execution.

---

## 🏗️ High-Level Interaction Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant CLI as CLI / Web UI
    participant Bus as CQRS CommandBus
    participant Brain as Brain Coordinator
    participant Guard as Security Guard
    participant Registry as Tool Registry
    participant LLM as Model Provider Adapter
    participant Memory as SQLite Memory

    User->>CLI: Input prompt / command
    CLI->>Brain: Process User Request
    Brain->>Memory: Retrieve Recent Context & Facts
    Brain->>LLM: Send Prompt + System Context + Tool Definitions
    LLM-->>Brain: Return Response (Text or Tool Call Request)
    
    alt Response is Tool Call Request
        Brain->>Guard: Evaluate Tool Execution Risk
        alt Risk == HIGH / CRITICAL and Strict Mode
            Guard-->>User: Request Explicit Approval
        end
        Brain->>Bus: Dispatch ExecuteToolCommand
        Bus->>Registry: Execute Target Tool
        Registry-->>Bus: Tool Result Output
        Bus-->>Brain: Return Tool Result
        Brain->>LLM: Send Tool Result to LLM for final synthesis
        LLM-->>Brain: Final Synthesized Text Response
    end
    
    Brain->>Memory: Persist Conversation Turn
    Brain-->>CLI: Display Output / Stream Response
    CLI-->>User: Render Response
```

---

## 🧩 Subsystem Responsibility Breakdown

| Subsystem | Responsibilities | Key Classes |
| :--- | :--- | :--- |
| **CLI / Gateway** | Interactive terminal shell, web dashboard server, user command parsing | `nexusai.cli.app`, `nexusai.api.server` |
| **CQRS Bus** | Decoupled message passing for Commands, Queries, and Events | `CommandBus`, `QueryBus`, `EventBus` |
| **Brain Coordinator** | Workflow graph execution, LLM prompt assembly, tool call routing | `BrainCoordinator`, `GraphWorkflow` |
| **Security Guard** | Risk classification (LOW..CRITICAL), command string sanitization | `SecurityGuard`, `CommandSanitizer` |
| **Tool Registry** | Registration, discovery, and schema validation of tool plugins | `ToolRegistry`, `BaseTool` |
| **Model Provider** | Model-agnostic adapter for OpenAI, Anthropic, Gemini, Ollama | `OpenAIProvider`, `BaseModelProvider` |
| **SQLite Memory** | Local storage for conversation history, system state, and facts | `SQLiteMemory`, `BaseMemory` |

---

## 🔄 Event-Driven Pipeline

All significant state changes emit asynchronous events onto the `EventBus`:
- `ToolExecutedEvent`: Published after any tool completes execution.
- `MemoryUpdatedEvent`: Published when new facts or turns are saved.
- `SecurityAlertEvent`: Published when a dangerous command is blocked.

This allows external monitors, web dashboards, and audit loggers to react without coupling to core business logic.
