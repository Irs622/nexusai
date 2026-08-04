---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - project-roadmap
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🗺️ NexusAI Product Roadmap

> [!NOTE]
> **Honesty Principle**: Targets listed reflect active planning milestones. Features marked as `In Progress` or `Planned` will update as implementations land.

---

## 📌 Milestones

### 🟢 v0.2.0-rc1 — Provider SDK RC (Certified Foundation)
- [x] Model-agnostic provider adapters (OpenRouter, Gemini, Anthropic, Ollama L5 Certified).
- [x] Provider SDK Foundation (`BaseProvider`, `ProviderRegistry`, `ProviderManager`, `ProviderRouter`).
- [x] Canonical Semantic Equivalence Suite (`test_canonical_equivalence.py`).
- [x] Governance & Canonical Evolution Rules (`ADR-0006`, `ADR-0007`).
- [x] CQRS Command, Query, and Event Bus (`src/nexusai/bus/`).
- [x] Interactive Terminal CLI Chat & Web Dashboard.
- [x] Security Guard & Command Sanitizer.
- [x] SQLite memory persistence.

### 🟡 Phase 2 — Developer Experience & Ecosystem (Active Focus)
- [x] **Phase 2.1 — Architecture Enforcement & Governance Suite** (AST Dependency Inspector, Data-Driven Rules A001-A006, Whitelist Manager, Drift Detection, Multi-Dimensional Health Dashboard, GitHub Actions CI).
- [x] **Phase 2.2A — Kernel Plugin Runtime Engine** (Formalized Plugin SDK, `BasePlugin`, discovery engine, `ManifestLoader`, `PluginValidator`, `DependencyResolver`, `ScopedPermissions`, `PluginSandbox`, `PluginRegistry`, `PluginRuntime`, `PluginLifecycleManager`).
- [x] **Phase 2.3 — Event Bus & Observability** (OpenTelemetry distributed tracing, token latency metrics, event replay, standardized event export).
- [ ] **Phase 2.4 — Memory Runtime Engine** (7 Milestones: Contracts, Storage Engine, Embedding Layer, Vector Store, Retrieval Pipeline, Event-Driven Integration, Policy Engine).
- [ ] **Phase 2.5 — Kernel Orchestration Engine** (Runtime Scheduler, Service Registry, Kernel Bootstrap, Lifecycle Coordinator, Graceful Shutdown, Health Check).
- [ ] **Phase 2.2B — Enterprise Plugin Runtime & Marketplace Hardening** (Ed25519 digital signatures, OpenTelemetry metrics exporter, OS process isolation, marketplace ecosystem).
- [ ] **Phase 2.6 — Technical Debt Refactoring & Developer CLI** (Clean up transitional re-exports, enforce DI Rules A007/A008, `nexusai` CLI suite).

### 🔵 Phase 3 — Observability & Tracing (Planned)
- [ ] OpenTelemetry distributed tracing integration for provider invocations.
- [ ] Standardized metrics export (token latency, request counts, error rates).
- [ ] Diagnostic profiling tools.

### 🟣 Phase 4 — Enterprise Resilience (Planned)
- [ ] Intelligent load balancing & dynamic provider failover.
- [ ] Cost optimization & budget token routing.
- [ ] Enterprise policy enforcement engine.
