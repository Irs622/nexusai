---
status: stable
audience:
  - contributors
owner:
  - core-team
applies_to:
  - contribution-workflow
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🤝 Contributing to NexusAI

Thank you for your interest in contributing to **NexusAI**! We welcome contributions from developers of all backgrounds.

---

## 📜 Definition of Done (DoD) Checklist

Before submitting a Pull Request, verify that your contribution meets our Definition of Done:

- [ ] All unit tests pass locally (`pytest`).
- [ ] Code passes static analysis (`ruff check .`, `mypy --strict src/nexusai`).
- [ ] New features include corresponding unit tests in `tests/unit/`.
- [ ] User-facing changes update `CHANGELOG.md` under `[Unreleased]`.
- [ ] Relevant documentation under `docs/` or `docs/specs/` is updated.
- [ ] Architectural shifts include an ADR in `docs/adr/`.

---

## 🔀 Branch & Commit Conventions

### Branch Naming
- `feature/short-description` for new capabilities.
- `fix/issue-description` for bug fixes.
- `docs/topic-name` for documentation improvements.

### Commit Messages (Conventional Commits)
We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature.
- `fix:` A bug fix.
- `docs:` Documentation only changes.
- `style:` Changes that do not affect the meaning of code (formatting).
- `refactor:` Code change that neither fixes a bug nor adds a feature.
- `test:` Adding missing tests or correcting existing tests.
- `chore:` Maintenance tasks or dependency updates.

---

## 🛠️ Local Development Setup

1. **Fork & Clone:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/nexusai.git
   cd nexusai
   ```

2. **Virtual Environment Setup:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Run Test Suite:**
   ```bash
   pytest
   ```

---

## 🤖 AI-Assisted Contributions

If you are using AI coding assistants or submitting AI-generated PRs, please review **[AGENTS.md](AGENTS.md)** for our mandatory AI contribution guidelines.
