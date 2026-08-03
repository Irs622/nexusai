# 🤖 NexusAI (Jarfis)

> **Personal AI Operating System for macOS (Apple Silicon)**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Security Policy](https://img.shields.io/badge/Security-Policy-green.svg)](SECURITY.md)
[![Code of Conduct](https://img.shields.io/badge/Code%20of%20Conduct-v2.1-purple.svg)](CODE_OF_CONDUCT.md)

NexusAI (also known as **Jarfis**) is an autonomous personal AI Operating System built specifically for macOS. It provides an intelligent desktop assistant capable of natural language interaction, ambient voice processing, system automation, workspace context awareness, tiered RAG knowledge retrieval, and multi-model LLM orchestration.

---

## 🌟 Key Features

- **Multi-Model LLM Routing**: Model-agnostic layer supporting OpenAI, Anthropic, Gemini, OpenRouter, and local Ollama models.
- **Interactive CLI & Web Dashboard**: Choose between a rich terminal experience or a modern web interface.
- **Ambient Voice Processing**: Hands-free interactions via Speech-to-Text (STT) and Text-to-Speech (TTS).
- **Workspace Context Engine**: Automatically indexes workspace files and code context for RAG knowledge retrieval.
- **Autonomous Tool System**: Built-in tools for system commands, web search, memory persistence, and file management with a security evaluator guard.
- **CQRS Architecture**: Clean separation of Commands, Queries, and Events built for maximum reliability and scalability.

---

## 🏗️ Architecture Overview

NexusAI is built adhering to **Clean Architecture**, **SOLID Principles**, and **CQRS**:

- `src/nexusai/core/`: Configuration, Dependency Injection container, base exceptions.
- `src/nexusai/bus/`: CQRS `CommandBus`, `QueryBus`, and asynchronous `EventBus`.
- `src/nexusai/services/`: Services (`BrainCoordinator`, `WorkspaceService`, `SQLiteMemory`, `ToolService`, `ModelService`).
- `src/nexusai/models/`: Model provider adapters (OpenAI, Anthropic, Gemini, OpenRouter, Ollama).
- `src/nexusai/security/`: Permission evaluator, risk classifier, and command sanitizer.
- `src/nexusai/cli/`: Interactive CLI app and web server launcher.

---

## 🚀 Quickstart

### Prerequisites

- macOS (Apple Silicon recommended)
- Python 3.12+
- `uv` (recommended package manager) or standard `pip`

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/jarfis-projek.git
   cd jarfis-projek
   ```

2. **Set up virtual environment & install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. **Configure API Keys:**
   Copy the example environment configuration and add your API Key(s):
   ```bash
   cp .env.example .env
   ```
   Open `.env` in your text editor and add your `OPENROUTER_API_KEY` or `OPENAI_API_KEY`.

---

## 💻 Usage Modes

NexusAI can be launched in three modes:

### 1. Interactive Terminal CLI Chat
```bash
./.venv/bin/python -m nexusai.cli.app chat
```

### 2. Web Dashboard Interface
```bash
./.venv/bin/python -m nexusai.cli.app web
```
Open your browser and navigate to `http://127.0.0.1:8000`.

### 3. Voice Interaction Mode
```bash
./.venv/bin/python -m nexusai.cli.app chat --voice
```

---

## 🧪 Running Tests

Run the test suite using `pytest`:

```bash
./.venv/bin/pytest
```

---

## 🛡️ Security

Security is built into NexusAI's core. All autonomous tool executions pass through a risk evaluator guard before execution.

For security policy details or to report a vulnerability, please read our [SECURITY.md](SECURITY.md).

---

## 🤝 Contributing

We welcome community contributions! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before submitting pull requests.

---

## 📜 License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.