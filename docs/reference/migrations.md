---
status: stable
audience:
  - core-developers
owner:
  - core-team
applies_to:
  - database-migrations
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔄 Storage & Database Migration Strategy

## 1. SQLite Schema Evolution
Schema changes to `conversation_turns` or fact storage tables in `SQLiteMemory` MUST include:
- Idempotent `CREATE TABLE IF NOT EXISTS` statements.
- `ALTER TABLE` column migrations with default fallback values.
- Downward migration backup steps before schema upgrades.
