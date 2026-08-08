# 🛡️ Security Policy

## Supported Versions

We actively release security patches for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.6.x   | :white_check_mark: |
| 0.5.x   | :white_check_mark: |
| < 0.5   | :x:                |

---

## 🔒 Secrets & API Key Policy

- **Zero Hardcoded Secrets**: **NEVER** embed hardcoded API keys, tokens, or dummy keys in source files, tests, or examples.
- **Dynamic Retrieval**: All credentials MUST be retrieved dynamically from environment variables (`os.getenv(...)`) or encrypted local storage.
- **Automated Scanning**: All commits and PRs are scanned with automated secret scanners (`pip-audit` and GitHub Secret Scanning).

---

## 🐛 Reporting a Vulnerability & Responsible Disclosure

We take the security of **NexusAI** seriously. If you discover a security vulnerability, please do **NOT** open a public GitHub issue.

Instead, please report vulnerabilities via one of the following channels:

1. **GitHub Private Vulnerability Reporting**: Use the "Report a vulnerability" button under the **Security** tab of this repository.
2. **Security Contact Email**: Send vulnerability reports directly to `security@nexusai.dev` (or the core maintainers).

### What to Include in Your Report

Please include as much detail as possible to help us reproduce and remediate the vulnerability quickly:

- **Type of Issue**: (e.g. prompt injection, privilege escalation, credential leak, arbitrary code execution)
- **Affected Subsystem**: (`nexusai.brain.runtime`, `nexusai.security`, `nexusai.api`, etc.)
- **Step-by-Step Reproduction**: Code snippet or payload required to trigger the issue
- **Potential Impact**: Assessment of risk severity and data exposure

---

## ⏱️ Response & Remediation Timeline

- **Acknowledgement**: Within 48 hours.
- **Triage & Status Update**: Within 5 business days.
- **Patch & Security Advisory Release**: Within 14 business days (depending on severity).

---

## 📦 Dependency Updates & Vulnerability Auditing

- We use Dependabot for automated dependency updates (`.github/dependabot.yml`).
- `pip-audit` is run as part of our automated CI quality gate (`make quality-gate`) to scan for known CVEs in third-party packages.
