---
status: stable
audience:
  - security-auditors
  - core-developers
owner:
  - security-team
applies_to:
  - tool-execution
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🛝 Tool Sandbox & Command Sanitization

## 1. Overview

To prevent arbitrary code execution attacks and prompt injection exploits, NexusAI subjects all terminal shell commands to strict pre-execution sanitization (`CommandSanitizer`).

---

## 🛑 Blacklisted Command Patterns

The following command patterns are hard-blocked by `config/security.yaml`:

- `rm -rf /`
- `rm -rf ~`
- `mkfs`
- `dd if=`
- `sudo rm -rf`
- Fork bombs (`:(){ :|:& };:`)

---

## 🔒 Path Protection Boundary

System paths are protected against unauthorized modification:
- `/System`
- `/usr/bin`
- `/bin`
- `/sbin`
- `/etc`
- `/var`
