---
status: stable
audience:
  - contributors
  - plugin-developers
owner:
  - core-team
applies_to:
  - codebase-layout
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🗺️ Project Structure Reference

This document maps out the source code directory layout under `src/nexusai/` to help contributors navigate the codebase efficiently.

---

## 📂 Source Code Layout (`src/nexusai/`)

```
src/nexusai/
├── __init__.py                # Package initialization
├── __main__.py                # Module entrypoint (python -m nexusai)
├── api/                       # Web Dashboard & REST Gateway
│   ├── __init__.py
│   └── server.py              # FastAPI server & route handlers
├── automation/                # Background Scheduling Subsystem
│   ├── __init__.py
│   └── scheduler.py           # APScheduler integration service
├── brain/                     # AI Orchestration & Workflow Engine
│   ├── __init__.py
│   ├── coordinator.py         # Main BrainCoordinator runtime
│   ├── prompt.py              # System prompt builders
│   └── workflow/              # LangGraph workflow state machine
│       ├── __init__.py
│       ├── graph.py           # StateGraph definition
│       ├── nodes.py           # State transition node handlers
│       └── state.py           # AgentState Pydantic definitions
├── bus/                       # CQRS Message Bus
│   ├── __init__.py
│   ├── bus.py                 # CommandBus, QueryBus, EventBus
│   ├── commands.py            # Command definitions (ExecuteToolCommand, etc.)
│   └── events.py              # Event definitions (ToolExecutedEvent, etc.)
├── cli/                       # Terminal User Interface
│   ├── __init__.py
│   ├── app.py                 # Typer CLI application commands
│   ├── chat.py                # Interactive Chat Loop
│   └── console.py             # Rich console output formatting
├── context/                   # Workspace Context Engine
│   ├── __init__.py
│   └── engine.py              # Workspace directory indexing
├── core/                      # Core Infrastructure & Configuration
│   ├── __init__.py
│   ├── config.py              # Pydantic Settings configuration loader
│   ├── container.py           # Dependency Injection Container
│   └── errors.py              # Custom exception hierarchy
├── knowledge/                 # Vector Store & Knowledge Retrieval
│   ├── __init__.py
│   └── vector.py              # ChromaDB vector store wrapper
├── logging/                   # Logging Setup
│   ├── __init__.py
│   └── logger.py              # Loguru configuration & audit sink
├── memory/                    # Persistent Memory Subsystem
│   ├── __init__.py
│   ├── base.py                # BaseMemory abstract interface
│   └── sqlite_memory.py       # SQLite persistent storage adapter
├── models/                    # LLM Provider Adapters
│   ├── __init__.py
│   ├── base.py                # BaseModelProvider abstract adapter interface
│   └── openai_provider.py     # OpenAI / OpenRouter / Ollama API provider
├── security/                  # Security & Permissions
│   ├── __init__.py
│   ├── guard.py               # SecurityGuard & Risk Classifier
│   └── sanitizer.py           # CommandSanitizer & blacklist evaluator
├── tools/                     # Tool Registry & Built-in Adapters
│   ├── __init__.py
│   ├── base.py                # BaseTool abstract base class
│   ├── registry.py            # ToolRegistry container
│   ├── automation/            # Timer & task tools
│   ├── knowledge/             # Memory & fact recall tools
│   ├── macos/                 # Native macOS AppleScript & window tools
│   ├── system/                # Terminal execution tools
│   ├── vision/                # Screen analysis & vision tools
│   └── workspace/             # File system & git tools
└── voice/                     # Voice STT & TTS Adapters
    ├── __init__.py
    ├── stt.py                 # Speech-to-Text adapter
    └── tts.py                 # Text-to-Speech adapter
```

---

## 🧪 Test Suite Layout (`tests/`)

```
tests/
├── conftest.py                # Pytest fixtures & mock containers
└── unit/                      # Unit test suite
    ├── test_api.py            # FastAPI route tests
    ├── test_automation.py     # Scheduler tests
    ├── test_brain.py          # Brain coordinator & LLM provider tests
    ├── test_bus.py            # CQRS bus tests
    ├── test_cli.py            # CLI app tests
    ├── test_config.py         # Config loading tests
    ├── test_context.py        # Context engine tests
    ├── test_memory.py         # SQLite memory tests
    ├── test_security.py       # Security guard & sanitizer tests
    └── test_tools.py          # Tool registry tests
```
