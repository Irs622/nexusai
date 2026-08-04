---
status: stable
audience:
  - developers
  - contributors
  - maintainers
  - architects
  - researchers
owner:
  - core-team
applies_to:
  - repository-wide
review_cycle: yearly
last_reviewed: 2026-08-04
---

# 🏛️ The NexusAI Architecture Manifesto

> **NexusAI: Model-Agnostic AI Operating System for Personal Intelligence Infrastructure**

---

## 📜 Project Governance & Evolution Cadence

This Manifesto serves as the constitutional document of the **NexusAI** project. All architectural decisions, design patterns, Architectural Decision Records (ADRs), Requests for Comments (RFCs), pull requests, and codebase implementations MUST comply with the directives set forth in this document.

```text
               ╔═══════════════════════════════════════╗
               ║        Architecture Manifesto        ║  (Rarely — Years)
               ║ (docs/concepts/architecture_manif.md) ║  (Requires Core Team Consensus)
               ╚═══════════╦═══════════════════════════╝
                           ║  (Governing Binding Rule:
                           ║   No ADR, RFC, or PR may
                           ║   violate the Manifesto)
                           ▼
               ╔═══════════════════════════════════════╗
               ║        Architecture Rationale        ║  (Rarely — Major Versions)
               ║ (docs/concepts/architecture_rat...md) ║  (Explains Why & Trade-Offs)
               ╚═══════════╦═══════════════════════════╝
                           ║
                           ▼
               ╔═══════════════════════════════════════╗
               ║   Architecture Decision Records (ADR) ║  (Occasionally — Quarterly)
               ║             (docs/adr/)               ║  (Gated Architecture Changes)
               ╚═══════════╦═══════════════════════════╝
                           ║
                           ▼
               ╔═══════════════════════════════════════╗
               ║       Request for Comments (RFC)      ║  (Frequently — Sprints)
               ║               (rfcs/)                 ║  (Feature Specifications)
               ╚═══════════╦═══════════════════════════╝
                           ║
                           ▼
               ╔═══════════════════════════════════════╗
               ║          Code Implementation          ║  (Continuously — Daily)
               ║             (src/nexusai/)            ║  (Standard PR Execution)
               ╚═══════════════════════════════════════╝
```

---

## 🔒 Five Architectural Invariants

The following five **Architectural Invariants** represent non-negotiable rules of system design. Every architectural proposal and pull request MUST satisfy all five invariants:

1. **Invariant 1: The User Owns the System.** All state, memory, workflows, plugins, configuration, and security policies belong strictly to the user.
2. **Invariant 2: The AI Does Not Own the State.** Foundation models process input tokens and generate output tokens. They hold zero persistent state, zero memory, and zero authority over system execution.
3. **Invariant 3: State Must Never Depend on Inference.** Conversational history, agent state machines, plugin capability registers, background schedules, and security policies MUST exist independently of LLM context windows or provider sessions.
4. **Invariant 4: Every Subsystem Must Expose an Abstract Interface.** Foundation models, vector databases, memory stores, UI shells, and system automation drivers MUST remain pluggable, modular, and replaceable via standard interfaces.
5. **Invariant 5: No Core Module May Depend on a Concrete Provider.** Core runtime, memory, security, and workflow packages MUST NOT import or depend on concrete provider adapter implementations.

---

## 🎯 Product Identity & Vision

```text
NexusAI
Model-Agnostic AI Operating System
for Personal Intelligence Infrastructure
```

- **Product Identity**: Model-Agnostic AI Operating System.
- **Domain Served**: Personal Intelligence Infrastructure.

Just as Unix decoupled application software from physical hardware, NexusAI decouples human intent, personal context, system workflows, and desktop automation from foundation models.

---

## 👑 Ownership Hierarchy

```text
                  ┌─────────────────────────────────────────┐
                  │                 USER                    │
                  │          (Sovereign Owner)              │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │            NexusAI OS Kernel            │
                  │  (Owns Memory, State, Workflows,        │
                  │   Plugins, Automation & Security)       │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │                AI Brain                 │
                  │    (Inference Compute Provider Only)    │
                  └─────────────────────────────────────────┘
```

- **User owns Memory**: Conversation history, personal knowledge graphs, entity relationships, and document embeddings reside strictly within local storage.
- **User owns Workflows**: Step-by-step automation sequences, schedules, and agent state machines are defined in declarative OS schemas.
- **User owns Plugins**: Installed system tools and automation capabilities interface exclusively with OS abstractions.
- **User owns Security**: Zero-trust risk classification and permission policies are governed locally.
- **Provider owns Inference Compute ONLY**: Foundation model providers process standardized input payloads and return structured tokens. They hold zero state, zero memory, and zero authority over system execution.

---

## 🚫 Explicit Non-Goals

NexusAI intentionally and permanently refrains from:

1. ❌ **Building Proprietary Foundation Models**: NexusAI will never train or release proprietary LLMs.
2. ❌ **Depending on a Single AI Vendor**: Features relying on closed vendor extensions unable to be mapped across canonical abstractions are forbidden.
3. ❌ **Storing User Memory Inside Provider Cloud APIs**: NexusAI will never store conversational state or thread history inside vendor-managed cloud session APIs.
4. ❌ **Treating Prompts as System State**: Prompts are transient instructions. System state resides strictly in typed databases, event logs, and workflow schemas.
5. ❌ **Tying Workflows to Specific Models**: Workflows are model-agnostic execution graphs with zero hardcoded vendor assumptions.
6. ❌ **Dishonestly Hiding Provider Differences**: Missing provider capabilities MUST be flagged explicitly rather than silently faked.
7. ❌ **Forcing User Subscriptions or Telemetry**: Zero subscription paywalls for core OS features, and zero telemetry harvesting of user data.

---

## 🏛️ Core Governing Principles

1. **Model Agnostic**: Zero model-specific logic in core kernel abstractions.
2. **Vendor Independence**: Equal status across all provider adapters.
3. **Persistent User Memory**: Multi-tiered local memory (SQLite & vector embeddings) independent of LLM context windows.
4. **Long-Term Agent Architecture**: Stateful background agents capable of recovery across system reboots.
5. **Plugin Ecosystem**: Minimalist kernel with modular tool extensions (`< 50 LOC`).
6. **Workflow Persistence**: Declarative multi-step workflows executed by a durable engine (`nexusai.workflow`).
7. **Replaceable AI Brain**: Swappable inference units per-request, per-agent, or policy route.
8. **Zero Vendor Lock-in**: Open, human-readable data formats (YAML, SQLite, JSON, Markdown).
9. **Local-First Execution**: Native offline execution whenever compute capabilities permit.
10. **Privacy by Design**: Zero telemetry, zero prompt harvesting, zero unauthorized network calls.
11. **Composable Architecture**: Full dependency injection via `ServiceContainer`.
12. **Capability over Model**: Routing based on verified capability flags (`Capability`), not model string names.
13. **Stable Public Contracts**: SemVer 2.0.0 compliance for all public APIs.
14. **Backward Compatibility**: Non-destructive schema migrations and backward-compatible plugin loading.
15. **Evidence-Driven Architecture (ADR-0007)**: Mandatory cross-provider evidence (minimum 2 independent providers) before canonical contract evolution.

---

## 🏗️ Module Dependency Architecture Rules

Dependencies MUST strictly point inward toward core domain abstractions:

```text
cli / api  (UI Layer)
     │
     ▼
  brain    (Agent Coordination)
     │
┌────┴──────────────────────────┬──────────────────────────┐
▼                               ▼                          ▼
workflow                       security                     memory / knowledge
│                               │                          │
└───────────────────────────────┼──────────────────────────┘
                                ▼
                             runtime   (Core Execution Kernel)
                                │
                                ▼
                            providers (Stateless SDK Transport Adapters)
```

### Dependency Rules:
1. `nexusai.providers` MUST NOT import `nexusai.runtime` or `nexusai.brain`.
2. `nexusai.core` domain MUST NOT import concrete provider adapters.
3. `nexusai.runtime` NEVER imports provider implementations.

---

## 🔄 Architecture Decision Lifecycle

```text
Idea Proposal ──► Request for Comments (RFC) ──► Technical Discussion ──► ADR ──► Implementation & PR ──► Architecture Review ──► Release
```

1. **Idea Proposal**: Open an issue detailing the architectural need or feature.
2. **RFC Proposal**: Draft an RFC in `rfcs/` for significant boundary or interface changes.
3. **ADR Recording**: Log an Architectural Decision Record in `docs/adr/` once consensus is reached.
4. **Implementation**: Build typed Python 3.12+ code passing `mypy --strict`.
5. **Architecture Review**: Validate against the Architecture Review Checklist.
6. **Release**: Document changes in `CHANGELOG.md`.

---

## 📋 Mandatory Architecture Review Checklist

Before accepting any ADR, RFC, or major Pull Request, maintainers MUST verify:

- [ ] **Invariant Check**: Does this change satisfy all 5 Architectural Invariants?
- [ ] **Dependency Check**: Does this change respect the Module Dependency Architecture rules?
- [ ] **Replaceability Check**: Does every newly introduced component remain pluggable?
- [ ] **Lock-in Check**: Is this change completely free of vendor-specific hardcoding?
- [ ] **Ownership Check**: Does user state, memory, and workflow control remain 100% with NexusAI?
- [ ] **Evidence Check (ADR-0007)**: If modifying canonical SDK contracts, is there verified evidence from at least TWO independent providers?

---

## ✅ Architectural Definition of Done (DoD)

A new subsystem or core architectural feature is considered **DONE** only when:

1. ✅ **Architecture Documented**: High-level specs written under `docs/concepts/` or `docs/specs/`.
2. ✅ **ADR Created**: Approved ADR logged under `docs/adr/` if system boundaries change.
3. ✅ **Public API Typed**: Complete Python 3.12+ type annotations passing `mypy --strict`.
4. ✅ **Contract Tests Exist**: Suite passing semantic equivalence tests (`test_canonical_equivalence.py`).
5. ✅ **Integration Tests Pass**: Unit, fault-injection, and integration test coverage established.
6. ✅ **Backward Compatibility Verified**: Schema migrations tested without breaking existing databases.
7. ✅ **Observability Implemented**: Immutable telemetry events emitted over `EventBus`.

---

*For detailed explanations, trade-off matrices, and maintainer FAQs, refer to the companion document: [`docs/concepts/architecture_rationale.md`](file:///Users/mac/Downloads/jarfis%20projek/docs/concepts/architecture_rationale.md).*

---

*End of Architecture Manifesto — NexusAI Core Architecture Team*
