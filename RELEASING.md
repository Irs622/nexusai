---
status: stable
audience:
  - maintainers
owner:
  - core-team
applies_to:
  - release-process
review_cycle: yearly
last_reviewed: 2026-08-03
---

# 🚀 Release Checklist & Process

This checklist defines the mandatory steps for tag releases of **NexusAI**.

---

## 🔒 Enforced Release Gate

Pushing a `v*` tag triggers `.github/workflows/release.yml`. The `release` job (build + GitHub Release publish) declares `needs: [release-validation]`, so it **never runs unless validation succeeds**. The `release-validation` job:

1. Verifies the tag equals `v` + `pyproject.toml` version.
2. Runs `python tools/run_quality_gate.py --release`, which covers:
   - Lint, format, and type checks
   - Architecture compliance and API compatibility snapshots
   - Test suite in `ci-pr` mode (unit, integration, contract)
   - Benchmark regression gate
   - Security audit
   - Fresh install validation

Run the same gate locally before tagging.

## 📋 Release Checklist

1. **Run the Release Quality Gate locally**:
   ```bash
   python tools/run_quality_gate.py --release
   ```
2. **Run Benchmark Checks**:
   ```bash
   python benchmarks/startup.py
   python benchmarks/memory_footprint.py
   python benchmarks/tool_latency.py
   ```
3. **Update `CHANGELOG.md`**: Move `[Unreleased]` items under new version header (e.g. `[0.2.0] - YYYY-MM-DD`).
4. **Bump Version Numbers**:
   - Update `pyproject.toml` (`version = "x.y.z"`).
   - Update `src/nexusai/__init__.py` (`__version__ = "x.y.z"`).
5. **Git Tag & Push**:
   ```bash
   git add .
   git commit -m "chore(release): prepare release vx.y.z"
   git tag -a vx.y.z -m "NexusAI Release vx.y.z"
   git push origin main --tags
   ```
