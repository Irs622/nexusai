---
status: stable
audience:
  - end-users
owner:
  - core-team
applies_to:
  - model-configuration
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🤖 Configuring Custom & Local LLMs

Learn how to connect local Ollama models or custom OpenAI-compatible proxies.

---

## 🦙 Ollama Local Setup

1. Start Ollama: `ollama run llama3:8b`
2. Configure `config/default.yaml`:
   ```yaml
   models:
     default_provider: "openai"
     default_model: "llama3:8b"
     base_url: "http://localhost:11434/v1"
   ```
