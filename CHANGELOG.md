---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - release-notes
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 📜 Changelog

All notable changes to **NexusAI** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `feat(providers)`: Sprint 5 Canonical Normalizations & Semantic Equivalence Suite across 4 provider translators (`OpenAITranslator`, `GeminiTranslator`, `AnthropicTranslator`, `OllamaTranslator`).
- `feat(providers)`: Add optional `Usage.reasoning_tokens` metric field to canonical `Usage` model mapped across OpenRouter, Gemini, and Anthropic.
- `feat(providers)`: Add `retry_after: float | None` attribute to `ProviderRateLimitError` and HTTP header parsing in `CanonicalErrorMapper`.
- `test(contracts)`: Add `test_canonical_equivalence.py` semantic equivalence test suite verifying request/response/tool/error contract translation integrity across all 4 vendor translators.
- `feat(providers)`: Add `OllamaProvider` local REST adapter for offline LLM execution (`http://localhost:11434`), supporting chat, streaming, embeddings, tags/models discovery, and health checks.
- Unit, Contract, Fault Injection, and Live integration test suites for `OllamaProvider`.
- Multi-Level Provider Certification L5 for `OllamaProvider` with 0 kernel mutations.
- Vendor-agnostic Provider SDK foundation (`BaseProvider`, `ProviderRegistry`, `ProviderManager`, `ProviderRouter`, typed contracts `ChatRequest`/`ChatResponse`, `JSONSchema`, and capability spectrum) under `nexusai.providers`.
- Architectural Decision Record `docs/adr/0007-canonical-model-evolution.md` for governing canonical model evolution rules.
- Architectural Decision Record `docs/adr/0006-provider-sdk.md`.
- Complete OSPO documentation suite (`docs/index.md`, `AGENTS.md`, `MANIFESTO.md`, `PHILOSOPHY.md`, `DESIGN.md`, `PROJECT_CHARTER.md`).
- Formal specifications for Runtime, Memory, Workflow, Plugins, Providers, and Tools under `docs/specs/`.
- Security architecture guides (`permission-model.md`, `tool-sandbox.md`, `threat-model.md`).

### Fixed
- Fixed circular import dependency between `nexusai.core.config`, `nexusai.security.guard`, and `nexusai.tools` package modules.
- Implemented `SystemConfig.load_from_yaml` classmethod and resolved Pydantic model rebuild annotations.

---

## [0.1.0-alpha] - 2026-08-03

### Added
- Core CQRS architecture (`CommandBus`, `QueryBus`, `EventBus`).
- Model-agnostic LLM provider interface (`BaseModelProvider`, `OpenAIProvider`).
- Interactive CLI application (`nexusai chat`, `nexusai status`).
- Web Dashboard interface (`nexusai web`).
- Security Guard and Risk Classifier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- Local SQLite memory storage (`SQLiteMemory`).
