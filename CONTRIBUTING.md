# 🤝 Contributing to NexusAI

Thank you for your interest in contributing to **NexusAI**! We welcome contributions from developers of all backgrounds.

---

## 🛠️ Repository Setup

1. **Fork & Clone:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/nexusai.git
   cd nexusai
   ```

2. **Virtual Environment & Dependencies Setup:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Verify Environment Installation:**
   ```bash
   make test-contract
   ```

---

## 🧪 Running Tests & Quality Gate

We enforce strict automated quality gates. Before submitting code:

```bash
# Run unit tests
make test-unit

# Run public API contract fitness tests
make test-contract

# Run architecture complexity checks
make test-architecture

# Run complete quality gate sequence
make quality-gate
```

---

## 🎨 Coding Style & Guidelines

- **Python Version**: Target Python 3.12+ features (e.g. `X | Y` type syntax, explicit annotations).
- **Formatters & Linters**: We use `ruff`, `black`, and `isort`. Run `make format` to format code automatically.
- **Type Annotations**: All public functions and methods MUST have explicit type annotations (`mypy --strict`).
- **Docstrings**: Use Google-style docstrings for all public classes, functions, and dataclasses.
- **Logging**: Use `loguru` (`from nexusai.logging.logger import logger`). Never use raw `print()`.

---

## 🔀 Branch Naming & Commit Conventions

### Branch Naming
- `feature/short-description` for new capabilities.
- `fix/issue-description` for bug fixes.
- `docs/topic-name` for documentation improvements.
- `refactor/component-name` for refactoring.

### Commit Messages (Conventional Commits)
We enforce the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` A new feature.
- `fix:` A bug fix.
- `docs:` Documentation only changes.
- `style:` Formatting or lint fixes.
- `refactor:` Code change that neither fixes a bug nor adds a feature.
- `test:` Adding or updating tests.
- `chore:` Maintenance tasks or dependency updates.

---

## 📥 Pull Request Process

1. **Create a Feature Branch**: Make your changes in a dedicated topic branch.
2. **Satisfy Definition of Done (DoD)**:
   - [ ] All unit and contract tests pass (`make quality-gate`).
   - [ ] Code passes static analysis (`make lint`, `make typecheck`).
   - [ ] New features include unit tests under `tests/unit/`.
   - [ ] `CHANGELOG.md` is updated under `[Unreleased]`.
   - [ ] Architecture changes include updated docs in `docs/architecture.md`.
3. **Submit PR**: Open a Pull Request against the `main` branch with a clear title and description using the PR template.

---

## 🐛 Issue Reporting & Security Contact

- **Bug Reports**: Open a GitHub Issue using the [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Feature Requests**: Open a GitHub Issue using the [Feature Request Template](.github/ISSUE_TEMPLATE/feature_request.md).
- **Security Vulnerabilities**: Do NOT open a public issue. See [`SECURITY.md`](SECURITY.md) for responsible disclosure procedures.

---

## 🤖 AI-Assisted Contributions

If you are using AI coding assistants or submitting AI-generated PRs, please review **[AGENTS.md](AGENTS.md)** for strict code conventions and constraints.
