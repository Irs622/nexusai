---
status: stable
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - provider-adapters
review_cycle: monthly
last_reviewed: 2026-08-04
---

# 🔍 Vendor Feature Gap Matrix

This document details specific vendor API capability gaps used by `ProviderRouter` for feature-based provider routing decisions.

---

## 📑 Detailed Feature Gap Inventory

| Feature | OpenRouter Adapter | Gemini Adapter | Anthropic Adapter | Ollama Local |
|---|---|---|---|---|
| **Structured Output (JSON Schema)** | ✅ Native (`response_format`) | ✅ Native (`responseSchema`) | ✅ Native (`tool_choice`) | 🟡 Partial |
| **Reasoning / Thinking Tokens** | 🟡 Model-dependent | ✅ Native (`thinkingConfig`) | ✅ Native (`thinking`) | 🟡 Model-dependent |
| **Prompt Context Caching** | ❌ N/A | ✅ Native (`cachedContent`) | ✅ Native (`prompt_caching`) | ❌ N/A |
| **Parallel Tool Calling** | 🟡 Model-dependent | ✅ Native | ✅ Native | ❌ N/A |
| **Vision / Multimodal Inputs** | 🟡 Model-dependent | ✅ Native | ✅ Native | 🟡 Model-dependent |
| **Streaming Response Deltas** | ✅ SSE Stream | ✅ Chunk Stream | ✅ Server Events | ✅ NDJSON Stream |
