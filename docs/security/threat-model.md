---
status: stable
audience:
  - security-auditors
  - architects
owner:
  - security-team
applies_to:
  - threat-analysis
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🛡️ Threat Model

## 1. Threat Vectors & Countermeasures

| Threat Vector | Potential Impact | Countermeasure |
| :--- | :--- | :--- |
| **Indirect Prompt Injection** | Untrusted web / text content attempts tool execution hijack | Parameter validation via Pydantic & Risk Guard |
| **Destructive Command Execution** | LLM attempts `rm -rf /` or malicious script execution | `CommandSanitizer` blacklist & `SecurityGuard` |
| **API Credential Leakage** | Hardcoded secrets committed to public repos | Local `.env` isolation in `.gitignore` & Pre-commit scan |
| **Data Exfiltration** | Remote SaaS tracking user code and prompts | Local-first storage (SQLite + ChromaDB) with zero telemetry |
