---
status: stable
audience:
  - end-users
  - contributors
owner:
  - core-team
applies_to:
  - system-compatibility
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 💻 System Compatibility Matrix

---

## 🖥️ Operating System Support

| OS Platform | Architecture | Support Level |
| :--- | :--- | :--- |
| **macOS 14+ (Sonoma, Sequoia)** | Apple Silicon (M1/M2/M3/M4) | Tier 1 (Primary & Fully Supported) |
| **macOS 13+ (Ventura)** | Intel x86_64 | Tier 2 (Best Effort) |
| **Linux (Ubuntu 22.04+)** | x86_64 / arm64 | Experimental CLI |
| **Windows 11** | x86_64 | Unsupported (WSL2 required) |

---

## 🐍 Python Version Matrix

| Python Version | Status |
| :--- | :--- |
| **Python 3.12** | Recommended & Fully Supported |
| **Python 3.11** | Supported |
| **Python 3.9 / 3.10** | Minimal Fallback |
| **< Python 3.9** | Unsupported |
