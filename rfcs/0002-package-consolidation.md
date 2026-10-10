---
status: draft
audience:
  - contributors
owner:
  - core-team
applies_to:
  - src/nexusai
review_cycle: yearly
last_reviewed: 2026-10-11
---

# RFC 0002: Konsolidasi Paket Ganda & Pemecahan `api/server.py`

- **Feature Name**: `package_consolidation`
- **Start Date**: `2026-10-11`
- **Author(s)**: `@irsalshydiq`
- **Status**: `Draft`

---

## 1. Summary
Beberapa konsep punya dua implementasi paralel (top-level dan di bawah `brain/`). RFC ini mengusulkan satu pemilik per konsep, lalu memecah `api/server.py` menjadi router per domain.

## 2. Motivation
Pasangan yang tumpang tindih saat ini:

| Top-level | Di dalam `brain/` |
|---|---|
| `context/` | `brain/context/` |
| `memory/` | `brain/memory/` |
| `plugins/` | `brain/plugins/` |
| `workflow/` | `brain/workflow/` |
| `runtime/` (termasuk `state_machine.py`) | `brain/runtime/`, `brain/state_machine.py` |
| `domain/models.py` | `brain/domain/` |

Di dalam `runtime/` sendiri juga ada pasangan `retry.py`/`retry_policy.py` dan `engine.py`/`execution_engine.py`.

Akibatnya: kontributor sulit tahu modul mana yang kanonik, logika terduplikasi, dan aturan DAG di AGENTS.md §2 berisiko dilanggar. `api/server.py` (2044 baris) mencampur wiring CORS, auth, dan semua route.

## 3. Detailed Design
1. Inventaris pemakaian tiap pasangan (grep import + coverage) dan tetapkan modul kanonik.
2. Modul non-kanonik menjadi shim re-export yang memancarkan `DeprecationWarning` (lifecycle 4 fase di AGENTS.md §6).
3. Pindahkan route `api/server.py` ke `api/routers/<domain>.py` (`APIRouter`). `server.py` hanya menjadi app factory + middleware.
4. Tambahkan test arsitektur (`tests/architecture`) yang melarang import baru ke modul yang sudah deprecated.

## 4. Drawbacks
Churn import yang besar, dan selama masa deprecation ada risiko konflik merge dengan branch lain.

## 5. Alternatives
Biarkan apa adanya dan cukup dokumentasikan modul kanonik. Alternatif ini lebih murah, tapi duplikasinya tetap ada.

## 6. Unresolved Questions
- Untuk `memory`, `context`, dan `runtime`: paket mana yang kanonik?
- Butuh ADR terpisah per pasangan, atau satu ADR payung?
