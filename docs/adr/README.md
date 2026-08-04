---
status: stable
audience:
  - architects
  - core-developers
  - contributors
owner:
  - core-team
applies_to:
  - architectural-decision-records
review_cycle: quarterly
last_reviewed: 2026-08-04
---

# 📜 Architectural Decision Records (ADRs) Index

This directory documents key architectural decisions made during the design and development of the NexusAI AI Operating System.

---

## 📑 ADR Index

| ADR ID | Title | Status | Scope |
|---|---|---|---|
| [ADR 0001](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0001-plugin-system.md) | Plugin System Architecture & Lifecycle Hooks | Accepted | Plugins |
| [ADR 0002](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0002-memory-storage.md) | Local SQLite Vector & Key-Value Memory Storage | Accepted | Memory |
| [ADR 0003](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0003-security-evaluator.md) | Command Security Guard & Risk Classification | Accepted | Security |
| [ADR 0004](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0004-provider-interface.md) | Model-Agnostic Provider Interface | Superseded by 0006 | Models |
| [ADR 0005](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0005-reasoning-and-observation-architecture.md) | Reasoning Engine & Observation Architecture | Accepted | Brain |
| [ADR 0006](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0006-provider-sdk.md) | Vendor-Agnostic Provider SDK Foundation & Architecture | Accepted | Provider SDK |
| [ADR 0007](file:///Users/mac/Downloads/jarfis%20projek/docs/adr/0007-canonical-model-evolution.md) | Governance Principles for Canonical Model Evolution | Accepted | Provider SDK |

---

## 📖 Guidelines for Creating New ADRs

1. File naming convention: `XXXX-short-title.md` (e.g., `0007-dependency-injection-container.md`).
2. Every ADR must contain YAML frontmatter (`status`, `audience`, `owner`, `applies_to`, `review_cycle`, `last_reviewed`).
3. Standard sections: **Context**, **Decision**, and **Consequences**.
