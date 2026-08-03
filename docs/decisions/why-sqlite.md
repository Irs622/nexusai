---
status: stable
audience:
  - contributors
owner:
  - core-team
applies_to:
  - memory-subsystem
review_cycle: yearly
last_reviewed: 2026-08-03
---

# Why SQLite?

## Decision Rationale
1. **Zero Configuration**: Embedded single-file database that runs natively without external server setups.
2. **Local-First Privacy**: Ensures all user conversation history remains stored locally.
3. **Async Support**: Native `aiosqlite` integration prevents blocking main loop threads.
