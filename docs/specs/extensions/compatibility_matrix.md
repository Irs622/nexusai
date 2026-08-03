---
status: stable
audience:
  - architects
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - provider-adapters
review_cycle: quarterly
last_reviewed: 2026-08-04
---

# 📊 Provider Compatibility & Capability Matrix

This matrix tracks supported capabilities and feature normalization across all planned provider adapters in NexusAI.

---

## 📑 Feature Compatibility Matrix

| Feature | OpenRouter Adapter | Gemini Adapter | Ollama Adapter (Local) | Anthropic Adapter | Mock Provider |
|---|---|---|---|---|---|
| **Chat Completion** | ✅ Native | ✅ Native | ✅ Native | ✅ Native | ✅ Native |
| **Streaming Chat** | ✅ Native | ✅ Native | ✅ Native | ✅ Native | ✅ Native |
| **Vector Embeddings** | ✅ Via API | ✅ Native | ✅ Local Model | ❌ N/A | ✅ Native |
| **Vision / Multimodal** | 🟡 Model-dependent | ✅ Native | 🟡 Model-dependent | ✅ Native | 🟡 Model-dependent |
| **Structured JSON Mode** | ✅ Native | ✅ Native | 🟡 Partial | ✅ Native | ✅ Native |
| **Tool / Function Calling** | ✅ Native | ✅ Native | 🟡 Model-dependent | ✅ Native | ✅ Native |
| **Parallel Tool Calling** | 🟡 Model-dependent | ✅ Native | ❌ N/A | ✅ Native | ✅ Native |
| **Reasoning / Thinking** | 🟡 Model-dependent | ✅ Native | 🟡 Model-dependent | ✅ Native | 🟡 Model-dependent |
| **Local Offline Execution**| ❌ Remote API | ❌ Remote API | ✅ Fully Offline | ❌ Remote API | ✅ Local Mock |
| **API Billing / Usage** | ✅ Token Cost | ✅ Token Cost | ❌ Zero Cost | ✅ Token Cost | ✅ Mock Cost |

---

## 🎯 Legend

- ✅ **Native**: Fully supported and normalized by the provider adapter.
- 🟡 **Partial / Model-dependent**: Supported depending on specific model selection or partial schema translation.
- ❌ **N/A / Unsupported**: Feature not supported by provider API or runtime environment.
