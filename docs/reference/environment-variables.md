---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - environment-variables
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔑 Environment Variables Reference

Environment variables take precedence over settings in `config/default.yaml`.

---

## 📋 Available Variables

| Variable | Description | Default | Required? |
| :--- | :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | OpenRouter API Key for multi-model LLM access | None | Optional |
| `OPENAI_API_KEY` | Direct OpenAI API Key | None | Optional |
| `OPENAI_BASE_URL` | Base URL override for custom OpenAI proxies / LM Studio | None | Optional |
| `NEXUSAI_LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` | Optional |
| `NEXUSAI_STRICT_MODE` | Enable strict security prompt for HIGH/CRITICAL commands | `false` | Optional |
