---
status: stable
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - provider-sdk
  - runtime-kernel
review_cycle: yearly
last_reviewed: 2026-08-04
---

# 🛡️ Evidence-First Refactoring Protocol

This protocol defines the strict mandatory 7-point checklist required BEFORE any refactoring or new abstraction is allowed into `nexusai.runtime` or `nexusai.providers`.

---

## 📋 Mandatory 7-Point Refactoring Checklist

Every proposed kernel refactor MUST satisfy ALL 7 checklist conditions:

1. **□ Shared Evidence**: Requirement appears in at least **TWO** real, validated provider implementations (e.g. OpenRouter + Gemini).
2. **□ Cost Justification**: Maintaining vendor-level workarounds is demonstrably more expensive than adding a kernel abstraction.
3. **□ Net Code Reduction**: The abstraction reduces overall repository lines of code (LOC).
4. **□ Cyclomatic Complexity Reduction**: The abstraction reduces overall cyclomatic complexity across provider adapters.
5. **□ Benchmark Compliance**: Framework overhead remains strictly **< 2.0 ms** (verified via `benchmarks/check_regressions.py`).
6. **□ Contract Verification**: Passes 100% of Level 1 API and Level 2 Behavior Contract Test suites.
7. **□ Zero Dependency Cycles**: Introduces zero circular dependency imports (verified via AST `test_architecture.py`).

> **Enforcement**: If any single condition is marked **FAIL**, the proposed refactoring is automatically **REJECTED** and logged in `docs/architecture/rejected_abstractions.md`.
