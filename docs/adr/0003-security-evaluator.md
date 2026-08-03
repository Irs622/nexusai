---
status: accepted
audience:
  - security-team
  - architects
owner:
  - security-team
applies_to:
  - security-subsystem
review_cycle: yearly
last_reviewed: 2026-08-03
---

# ADR 0003: Security Guard & Risk Classification Model

## Context
Autonomous tool execution presents security risks if LLMs generate destructive shell commands.

## Decision
We implement a zero-trust `SecurityGuard` that evaluates tool execution requests against a risk matrix (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) and sanitizes shell parameters (`CommandSanitizer`).

## Consequences
- **Positive**: Prevents dangerous prompt injection and arbitrary command execution.
- **Negative**: Adds a negligible pre-execution validation overhead (~12ms).
