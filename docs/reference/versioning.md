---
status: stable
audience:
  - end-users
  - plugin-developers
  - maintainers
owner:
  - core-team
applies_to:
  - release-lifecycle
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔄 Versioning & Deprecation Policy

NexusAI strictly follows [Semantic Versioning 2.0.0](https://semver.org/) (`MAJOR.MINOR.PATCH`).

---

## 📌 Versioning Rules

- **MAJOR (`x.0.0`)**: Incompatible API changes, breaking plugin SDK changes, or schema revisions.
- **MINOR (`0.x.0`)**: New backwards-compatible functionality, new tool plugins, or new provider adapters.
- **PATCH (`0.0.x`)**: Backwards-compatible bug fixes and security security patches.

---

## ⏳ Deprecation Lifecycle Policy

1. **Announcement**: Deprecated APIs will emit a `DeprecationWarning` in Python for at least 1 MINOR release cycle before removal.
2. **Migration Guide**: Deprecations will be documented in `docs/reference/versioning.md` and `CHANGELOG.md` along with alternative migration paths.
