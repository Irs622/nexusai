---
status: active
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - repository-wide
review_cycle: monthly
last_reviewed: 2026-08-04
---

# 💳 Architecture Debt Register

This document tracks internal technical debt and design compromises in the NexusAI codebase.

> **Debt vs Pain Point**: Technical Debt represents internal code or structural compromises we control. Vendor Pain Points represent external API friction from third-party vendor APIs.

---

## 📋 Technical Debt Inventory

### AD-001: OpenAI Wire Format Duplication in Translators
- **Debt ID**: `AD-001`
- **Description**: `OpenAITranslator` is currently instantiated directly by `OpenRouterProvider`. As more OpenAI-compatible providers emerge, translator initialization logic should be resolved via dependency injection.
- **Impact**: Low
- **Interest**: Low (Only affects openrouter adapter initialization)
- **Due Date**: Post SDK 1.0 Freeze
- **Owner**: Architecture Team
- **Status**: `LOGGED — Low Priority`

### AD-002: Dynamic Compatibility Matrix Generator Runtime Dependency
- **Debt ID**: `AD-002`
- **Description**: `tools/generate_compatibility_matrix.py` imports `ProviderRegistry` directly rather than running as a standalone CI inspection step.
- **Impact**: Low
- **Interest**: Low
- **Due Date**: Post SDK 1.0 Freeze
- **Owner**: DevOps / Tooling Team
- **Status**: `LOGGED — Low Priority`
