---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - configuration-subsystem
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# ⚙️ Configuration Reference

NexusAI uses Pydantic Settings and YAML configuration files under `config/`.

---

## 📄 `config/default.yaml`

```yaml
app:
  name: "NexusAI"
  version: "0.1.0"
  environment: "development"
  debug: true

logging:
  level: "INFO"
  file_path: "logs/nexusai.log"
  audit_log_path: "logs/audit.log"

models:
  default_provider: "openrouter"
  default_model: "openrouter/auto"
  base_url: "https://openrouter.ai/api/v1"
  temperature: 0.7
  max_tokens: 2048
  timeout_seconds: 60
```

---

## 🛡️ `config/security.yaml`

```yaml
security:
  strict_mode: false
  auto_approve_low_risk: true
  
  forbidden_commands:
    - "rm -rf /"
    - "rm -rf ~"
    - "mkfs"
    - "dd if="
    - "sudo rm -rf"
  
  protected_paths:
    - "/System"
    - "/usr/bin"
    - "/bin"
    - "/etc"
```
