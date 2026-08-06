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

### ⚠️ Breaking Changes & API Migration Notes — Phase 2.6B

#### `ProviderProfile` constructor refactored
- **Before:** `ProviderProfile(provider_id="x", models=[...], average_latency_ms=...)`
- **After:** `ProviderProfile(metadata=ProviderMetadata(provider_id="x", display_name="..."))`
- **Migration:** Wrap provider static identity into `ProviderMetadata` instance and pass as `metadata=` keyword argument.

#### `ExecutionContext` cancellation token sub-context restructuring
- **Before:** `ExecutionContext(cancellation_token=token)`
- **After:** `ctx = ExecutionContext(); token = ctx.runtime.cancellation_token`
- **Migration:** Access cancellation token via `context.runtime.cancellation_token`.

#### `EmbeddingCapabilities` field renaming
- **Before:** `EmbeddingCapabilities(max_dimension=768, supports_gpu=True)`
- **After:** `EmbeddingCapabilities(dimensions=768)`
- **Migration:** Use `dimensions=` instead of `max_dimension=`. Remove obsolete `supports_gpu=` attribute.

#### `ModelInfo` and `ProviderHealth` field alignment
- **Before:** `model.name`, `health.model_count`
- **After:** `model.id`, `health.available_models`
- **Migration:** Use `.id` for `ModelInfo` primary identifier; use `.available_models` for `ProviderHealth` metric.

### Added — Phase 2.6B + 2.6C: Baseline Stabilization & RC Validation Gate

- `feat(quality)`: Tiered test execution matrix via `tools/run_tests.py` with `--mode` options (`local`, `unit`, `ci-pr`, `nightly`, `all`, `integration`, `contract`, `network`, `snapshot`, `architecture`).
- `feat(quality)`: Pytest test matrix marker registration in `pyproject.toml` (`unit`, `integration`, `contract`, `benchmark`, `stress`, `network`, `snapshot`, `architecture`, `security`, `slow`).
- `feat(api)`: Golden API Compatibility snapshot test suite in `tests/api_compatibility/` covering 6 frozen public API contracts (`ProviderProfile`, `ProviderMetadata`, `ProviderHealth`, `EmbeddingCapabilities`, `MemoryRecord`, `ExecutionContext`).
- `feat(quality)`: Cross-platform Python-native fresh installation verification script `tools/verify_fresh_install.py`.
- `docs(architecture)`: Added `docs/architecture/api_freeze.md` (3-tier governance policy: Stable, Beta, Experimental) and `docs/architecture/compatibility_matrix.md`.
- `feat(quality)`: Updated `tools/run_quality_gate.py` with `--release` mode support executing full verification sequence.

### Added — Phase 2.6: Engineering Quality Gate

- `chore(quality)`: Modular tool runner architecture under `tools/` — separate single-responsibility scripts for formatting (`run_formatter.py`), linting (`run_linter.py`), type checking (`run_typecheck.py`), test execution (`run_tests.py`), mutation testing (`run_mutation_tests.py`), benchmark pipeline (`run_benchmarks.py`), security audit (`run_security_audit.py`), and license compliance (`run_license_check.py`).
- `chore(quality)`: `tools/run_quality_gate.py` — local developer master orchestrator executing Stage 1 (formatter, linter, typecheck) in parallel via `concurrent.futures`, followed by sequential Stage 2 (architecture, tests, benchmarks).
- `chore(ci)`: Updated GitHub Actions workflows — `lint.yml` now correctly runs `run_formatter.py`, `run_linter.py`, and `run_typecheck.py` instead of incorrectly running pytest; `tests.yml` delegates to `run_tests.py`; `ci.yml` delegates to `run_quality_gate.py`.
- `chore(quality)`: `.pre-commit-config.yaml` — standard pre-commit configuration with ruff, black, isort, mypy, and file hygiene hooks.
- `chore(benchmark)`: Pluggable benchmark framework with `benchmarks/collectors/`, `benchmarks/comparators/`, and `benchmarks/reporters/` sub-packages.
- `chore(benchmark)`: Benchmark trend reporting with `Current`, `Previous`, `Delta (%)`, and `PASS/FAIL` status per metric.
- `chore(benchmark)`: Restructured `benchmarks/history/` into `history/baseline/` (committed baselines) and `history/runs/` (timestamped run snapshots).
- `chore(benchmark)`: `benchmarks/check_regressions.py` updated to delegate to the new pluggable benchmark framework instead of static file check.
- `test(kernel)`: `tests/kernel/test_kernel_extreme_stress.py` — extreme stress test suite covering: 10,000 concurrent async task submissions, 100-service rapid startup, rapid shutdown under 500 in-flight jobs, queue flooding via 5×1,000 burst enqueue, dependency graph concurrent resolution (100 parallel queries), and concurrent registry registration contention (200 services).
- `chore(security)`: `tools/run_security_audit.py` — `pip-audit` CVE vulnerability scanner integration.
- `chore(security)`: `tools/run_license_check.py` — dependency license compliance checker (GPL blocked, MIT/Apache/BSD allowed).
- `chore(config)`: `pyproject.toml` updated with `isort`, `mutmut`, `pip-audit`, `pip-licenses` dev dependencies; `[tool.coverage.run]` with branch coverage; `[tool.coverage.report]` with `fail_under = 90`; `[tool.mutmut]` scoped to `core/kernel/memory/domain`.
- `docs(engineering)`: `docs/engineering/quality_gate.md` — complete engineering quality reference guide.

### Added — Phase 2.5: Kernel Orchestration Engine
- `feat(kernel)`: Phase 2.5 Kernel Orchestration Engine implementing deterministic boot, topological dependency resolution, state machine lifecycle coordination with automated rollback protection (`ROLLING_BACK`), time-based `RuntimeScheduler`, queue-based `BackgroundWorkerManager`, and structured diagnostic `SnapshotManager`.
- `feat(kernel)`: Facade-driven `KernelOrchestrator` delegating to specialized kernel managers and exposing aggregated health/metrics across subsystems.
- `test(kernel)`: Complete unit test suite for service registry, dependency graph DAG, lifecycle coordinator, runtime scheduler, worker manager, snapshot manager, and kernel orchestrator.
- `test(acceptance)`: End-to-end acceptance tests validating boot failure recovery and restart after failure capabilities.
- `docs(kernel)`: Architecture guide for `docs/architecture/kernel_orchestration.md`.

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
