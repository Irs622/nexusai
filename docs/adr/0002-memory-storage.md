---
status: accepted
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - memory-subsystem
review_cycle: yearly
last_reviewed: 2026-08-03
---

# ADR 0002: Dual-Tier Local Memory Architecture

## Context
NexusAI needs persistent short-term conversation history and long-term vector indexing while adhering to local-first privacy rules.

## Decision
We store conversation turns in SQLite (`aiosqlite`) and episodic memory embeddings in ChromaDB local vector store.

## Consequences
- **Positive**: 100% offline, zero data exfiltration, fast local lookups.
- **Negative**: Requires local disk storage allocation for vector collections.
