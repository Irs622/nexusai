---
status: stable
audience:
  - end-users
  - contributors
  - security-auditors
owner:
  - security-team
applies_to:
  - security-subsystem
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🔑 Permission Model & Risk Evaluation

## 1. Overview

The **NexusAI Permission Model** classifies every tool invocation into one of four risk levels to prevent unauthorized or destructive execution.

---

## 🚦 Risk Classification Matrix

```mermaid
quadrantChart
    title Risk Evaluation Matrix
    x-axis Low System Impact --> High System Impact
    y-axis Read-Only --> State-Modifying
    "LOW: Get Time / Facts": [0.1, 0.1]
    "MEDIUM: Browser Tab / App Open": [0.3, 0.6]
    "HIGH: File Edit / Write": [0.7, 0.7]
    "CRITICAL: Terminal Shell / Subprocess": [0.9, 0.9]
```

### Risk Level Definitions

1. **`LOW` (Auto-Approved)**
   - Read-only operations, memory recall, active window queries.
2. **`MEDIUM` (Logged)**
   - Reversible UI actions, opening apps, non-destructive queries.
3. **`HIGH` (User Prompt in Strict Mode)**
   - File system writes, configuration overrides, system notifications.
4. **`CRITICAL` (Explicit Confirmation Required)**
   - Subprocess terminal execution, shell scripts, AppleScript automation.
