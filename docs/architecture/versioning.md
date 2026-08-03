---
status: stable
audience:
  - architects
  - core-developers
  - plugin-developers
owner:
  - core-team
applies_to:
  - sdk-public-api
review_cycle: yearly
last_reviewed: 2026-08-04
---

# 📦 Provider SDK Versioning & Governance Policy

This document defines the Semantic Versioning (`MAJOR.MINOR.PATCH`) policy for the public SDK interfaces in `nexusai.providers` and `nexusai.runtime`.

---

## 1. Frozen Public API (SDK 1.0.0+)

The following symbols represent frozen public API contracts:

- `BaseProvider` (`metadata`, `id`, `chat`, `stream_chat`, `embeddings`, `list_models`, `health_check`, `describe`, `initialize`, `shutdown`)
- `ChatMessage`, `ChatChoice`, `ChatRequest`, `ChatResponse`, `Usage`, `ToolSchema`, `JSONSchema`
- `ProviderMetadata`, `ProviderCapabilities`, `ProviderConfig`, `ProviderHealth`
- `ProviderRegistry`, `ProviderManager`, `ProviderRouter`, `ExecutionEngine`

---

## 2. Versioning Policy

- **PATCH Release (`1.0.x`)**: Bug fixes, performance optimizations, or internal implementation refactoring without altering method signatures or model fields.
- **MINOR Release (`1.x.0`)**: Backward-compatible additive enhancements (e.g. adding new optional capability flags or helper methods).
- **MAJOR Release (`x.0.0`)**: Breaking changes to public interfaces or models.

---

## 3. Deprecation Process

Any breaking change or method deprecation MUST follow a 3-step cycle:

1. **Deprecation Notice**: Mark symbol with `@deprecated` decorator and document in `CHANGELOG.md`.
2. **Migration Guide**: Publish a migration guide under `docs/migrations/`.
3. **Major Bump**: Remove deprecated symbol ONLY in the next MAJOR version release (`2.0.0`).
