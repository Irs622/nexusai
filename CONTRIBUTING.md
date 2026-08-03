# Contributing to NexusAI

Thank you for your interest in contributing to **NexusAI**! We welcome contributions from developers of all skill levels.

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

---

## How Can I Contribute?

### 1. Reporting Bugs
- Search existing [GitHub Issues](../../issues) to check if the bug has already been reported.
- If not, open a new issue using the **Bug Report** template.
- Include OS details, Python version, steps to reproduce, and error logs.

### 2. Suggesting Enhancements
- Open a **Feature Request** issue detailing the proposed change, use case, and potential benefits.

### 3. Submitting Pull Requests (PRs)

1. **Fork the Repository** and clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/jarfis-projek.git
   cd jarfis-projek
   ```

2. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/amazing-new-feature
   ```

3. **Set Up Development Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

4. **Make Your Changes**:
   - Follow PEP 8 style guidelines.
   - Add unit tests for any new features or bug fixes under `tests/`.

5. **Run Tests & Linting**:
   ```bash
   pytest
   ```

6. **Commit & Push**:
   ```bash
   git add .
   git commit -m "feat: add amazing new feature"
   git push origin feature/amazing-new-feature
   ```

7. **Open a Pull Request** against the `main` branch.

---

## Commit Message Guidelines

We follow Conventional Commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Formatting, missing semi colons, etc.
- `refactor:` Code refactoring without behavioral change
- `test:` Adding or updating tests
- `chore:` Build process or auxiliary tool changes

Thank you for building NexusAI with us! 🚀
