---
status: stable
audience:
  - end-users
  - plugin-developers
owner:
  - core-team
applies_to:
  - model-providers
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🤖 Supported AI Providers Guide

NexusAI features a model-agnostic LLM provider abstraction layer (`BaseModelProvider`).

---

## 📋 Provider Support Matrix

| Provider | Type | Recommended Models | Environment Variable |
| :--- | :--- | :--- | :--- |
| **OpenRouter** | Cloud Proxy | `openrouter/auto`, `anthropic/claude-3.5-sonnet` | `OPENROUTER_API_KEY` |
| **OpenAI** | Direct Cloud API | `gpt-4o`, `gpt-4o-mini` | `OPENAI_API_KEY` |
| **Ollama** | Local Offline | `llama3:8b`, `qwen2.5:coder` | None (Local `localhost:11434`) |
| **LM Studio** | Local OpenAI Proxy | Any local GGUF model | `OPENAI_BASE_URL=http://localhost:1234/v1` |

---

## ⚙️ Configuration Example (`config/default.yaml`)

```yaml
models:
  default_provider: "openrouter"
  default_model: "openrouter/auto"
  base_url: "https://openrouter.ai/api/v1"
  temperature: 0.7
  max_tokens: 2048
```
