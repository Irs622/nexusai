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
- Complete OSPO documentation suite (`docs/index.md`, `AGENTS.md`, `MANIFESTO.md`, `PHILOSOPHY.md`, `DESIGN.md`, `PROJECT_CHARTER.md`).
- Formal specifications for Runtime, Memory, Workflow, Plugins, Providers, and Tools under `docs/specs/`.
- Security architecture guides (`permission-model.md`, `tool-sandbox.md`, `threat-model.md`).

---

## [0.1.0-alpha] - 2026-08-03

### Added
- Core CQRS architecture (`CommandBus`, `QueryBus`, `EventBus`).
- Model-agnostic LLM provider interface (`BaseModelProvider`, `OpenAIProvider`).
- Interactive CLI application (`nexusai chat`, `nexusai status`).
- Web Dashboard interface (`nexusai web`).
- Security Guard and Risk Classifier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- Local SQLite memory storage (`SQLiteMemory`).
