---
status: stable
audience:
  - contributors
  - maintainers
owner:
  - core-team
applies_to:
  - rfc-process
review_cycle: yearly
last_reviewed: 2026-08-03
---

# 📄 RFC Process & Guidelines

## 1. What Requires an RFC?

You MUST submit an RFC for:
- Large architectural refactoring across core boundaries (`bus/`, `brain/`, `security/`).
- Breaking changes to public interfaces (`BaseTool`, `BaseModelProvider`).
- Introducing new core framework dependencies.

---

## 2. RFC Lifecycle Stages

1. **`Draft`**: Initial proposal submitted as a PR using `rfcs/RFC_TEMPLATE.md`.
2. **`Discussion`**: Open review and community feedback on GitHub PR.
3. **`Accepted`**: Approved by Maintainers.
4. **`Implemented`**: Code implementation merged into `main`.
5. **`Archived`**: Historical reference.
