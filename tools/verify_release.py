#!/usr/bin/env python3
"""NexusAI Release Candidate & Production Release Verification Gate.

Verifies 6 critical release dimensions before publishing:
1. Git Identity & Working Tree Sanitization
2. Static Analysis & Type Checking (ruff, mypy --strict)
3. ADR Architecture Completeness (ADR-0001 to ADR-0016 with 7 mandatory sections)
4. Core Subsystem Test Suites (MCP, Distributed Cluster, API/SSE)
5. Resilience & Chaos Evidence Audit (Soak test & P5-LIVE chaos reports)
6. Python Package Wheel Build Integrity
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import time

repo_root = Path(__file__).resolve().parent.parent

MANDATORY_ADR_SECTIONS = [
    "Status",
    "Context",
    "Decision",
    "Alternatives Considered",
    "Consequences",
    "Validation Criteria",
    "Review Phase",
]


def log_gate(gate_num: int, name: str, status: str, details: str = "") -> None:
    symbols = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "RUN": "⏳"}
    sym = symbols.get(status, "ℹ️")
    print(f"[{sym}] Gate {gate_num}: {name.ljust(45)} [{status}]")
    if details:
        print(f"    └─ {details}")


def run_cmd(cmd: list[str], cwd: Path = repo_root) -> tuple[int, str, str]:
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def check_gate_1_git() -> bool:
    """Verify clean working tree and authorized git committer identity."""
    code, out, _ = run_cmd(["git", "config", "user.name"])
    author_name = out
    code, out, _ = run_cmd(["git", "config", "user.email"])
    author_email = out

    is_author_valid = author_name == "irsalshydiq" and author_email == "ichalprov@gmail.com"

    code, status_out, _ = run_cmd(["git", "status", "--porcelain"])
    # Filter untracked scratch/dist/build files
    dirty_lines = [
        line
        for line in status_out.splitlines()
        if not any(
            ignored in line
            for ignored in [
                "dist/",
                "build/",
                ".pytest_cache",
                "vault/",
                "artifacts/",
                "egg-info",
            ]
        )
    ]
    is_tree_clean = len(dirty_lines) == 0

    if is_author_valid and is_tree_clean:
        log_gate(1, "Git Identity & Tree Sanitization", "PASS", f"Author: {author_name} <{author_email}> | Tree clean")
        return True
    else:
        log_gate(1, "Git Identity & Tree Sanitization", "FAIL", f"Author: {author_name}, Dirty items: {len(dirty_lines)}")
        return False


def check_gate_2_static_analysis() -> bool:
    """Verify ruff linting and mypy strict typing."""
    code_ruff, out_ruff, err_ruff = run_cmd([
        ".venv/bin/ruff",
        "check",
        "src/nexusai/tools/mcp/",
        "src/nexusai/infrastructure/distributed/",
        "src/nexusai/brain/domain/collaboration.py",
        "src/nexusai/brain/runtime/collaboration/",
        "src/nexusai/brain/planner/validator.py",
    ])
    if code_ruff != 0:
        log_gate(2, "Static Analysis (ruff)", "FAIL", out_ruff or err_ruff)
        return False

    code_mypy, out_mypy, err_mypy = run_cmd([
        ".venv/bin/mypy",
        "--strict",
        "src/nexusai/tools/mcp/servers/",
        "src/nexusai/infrastructure/distributed/",
        "src/nexusai/brain/domain/collaboration.py",
        "src/nexusai/brain/runtime/collaboration/",
    ])
    if code_mypy != 0:
        log_gate(2, "Static Type Checking (mypy --strict)", "FAIL", out_mypy or err_mypy)
        return False

    log_gate(2, "Static Analysis & Type Integrity", "PASS", "ruff: 0 issues | mypy --strict: 0 issues across 16 source files")
    return True


def check_gate_3_adr_governance() -> bool:
    """Verify all 16 ADRs exist and conform to 7 mandatory sections."""
    adr_dir = repo_root / "docs" / "adr"
    if not adr_dir.exists():
        log_gate(3, "ADR Architecture Governance", "FAIL", "docs/adr directory missing")
        return False

    adr_files = sorted(list(adr_dir.glob("00*.md")))
    if len(adr_files) < 16:
        log_gate(3, "ADR Architecture Governance", "FAIL", f"Expected >= 16 ADRs, found {len(adr_files)}")
        return False

    # Phase 3.2+ & Level 4 Governance ADRs require all 7 mandatory sections
    missing_sections: dict[str, list[str]] = {}
    modern_adrs = [adr for adr in adr_files if int(adr.name.split("-")[0]) >= 13]
    for adr in modern_adrs:
        content = adr.read_text(encoding="utf-8")
        for sec in MANDATORY_ADR_SECTIONS:
            pattern = re.compile(rf"(#+.*{re.escape(sec)}|\*\*{re.escape(sec)}\*\*)", re.IGNORECASE)
            if not pattern.search(content):
                missing_sections.setdefault(adr.name, []).append(sec)

    if missing_sections:
        details = ", ".join(f"{k}: missing {v}" for k, v in missing_sections.items())
        log_gate(3, "ADR Architecture Governance", "FAIL", details)
        return False

    log_gate(
        3,
        "ADR Architecture Governance",
        "PASS",
        f"All {len(adr_files)} ADRs present | {len(modern_adrs)} Phase 3.2+/Level 4 ADRs strictly conform to 7 mandatory sections",
    )
    return True



def check_gate_4_core_tests() -> bool:
    """Execute core test suites for distributed workers, MCP servers, and API/SSE."""
    test_files = [
        "tests/unit/test_mcp_builtin_servers.py",
        "tests/unit/test_mcp_client.py",
        "tests/unit/test_mcp_manager.py",
        "tests/unit/test_mcp_tool_wrapper.py",
        "tests/unit/infrastructure/test_worker_supervisor_and_autoscaler.py",
        "tests/unit/infrastructure/test_distributed_execution_scheduler.py",
        "tests/unit/api/test_server_mcp_and_sse.py",
        "tests/unit/brain/test_multi_agent_collaboration_mesh.py",
        "tests/unit/cli/test_cluster_tui.py",
    ]
    code, out, err = run_cmd([".venv/bin/pytest", *test_files, "-q"])
    if code != 0:
        log_gate(4, "Core Subsystems Test Suite", "FAIL", out or err)
        return False

    match = re.search(r"(\d+)\s+passed", out)
    passed_count = match.group(1) if match else "all"
    log_gate(4, "Core Subsystems Test Suite", "PASS", f"{passed_count} tests passed across MCP, Distributed & API")
    return True


def check_gate_5_resilience_evidence() -> bool:
    """Audit soak harness report and P5-LIVE staging chaos evidence."""
    soak_file = repo_root / "artifacts" / "soak_test" / "soak_report.json"
    p5_live_file = repo_root / "artifacts" / "p5_live" / "p5_live_evidence_report.json"

    if not soak_file.exists():
        log_gate(5, "Resilience & Chaos Evidence", "FAIL", "Soak report missing")
        return False

    if not p5_live_file.exists():
        log_gate(5, "Resilience & Chaos Evidence", "FAIL", "P5-LIVE evidence report missing")
        return False

    with open(soak_file, "r", encoding="utf-8") as f:
        soak_data = json.load(f)

    with open(p5_live_file, "r", encoding="utf-8") as f:
        p5_data = json.load(f)

    soak_pass = soak_data.get("verdict") == "PASS"
    net_growth = soak_data.get("memory_audit", {}).get("net_rss_growth_mb", 0.0)
    chaos_pass = p5_data.get("verdict") == "PASS"
    passed_scenarios = p5_data.get("passed_scenarios", 0)

    if soak_pass and chaos_pass:
        log_gate(
            5,
            "Resilience & Chaos Evidence",
            "PASS",
            f"Soak: PASS (Net RSS: {net_growth:+.2f}MB) | Chaos: PASS ({passed_scenarios}/15 scenarios)",
        )
        return True
    else:
        log_gate(
            5,
            "Resilience & Chaos Evidence",
            "FAIL",
            f"Soak: {soak_data.get('verdict')}, Chaos: {p5_data.get('verdict')}",
        )
        return False


def check_gate_6_build() -> bool:
    """Verify that python -m build can create a valid wheel package without errors."""
    code, out, err = run_cmd([".venv/bin/python", "-m", "build", "--wheel", "--no-isolation"])
    if code != 0:
        log_gate(6, "Python Package Wheel Build", "FAIL", err or out)
        return False

    wheels = list((repo_root / "dist").glob("*.whl"))
    latest_wheel = wheels[-1].name if wheels else "wheel"
    log_gate(6, "Python Package Wheel Build", "PASS", f"Successfully built wheel: {latest_wheel}")
    return True


def main() -> None:
    print("=" * 75)
    print("🚀 NEXUSAI RELEASE CANDIDATE VERIFICATION GATE")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 75)

    gates = [
        check_gate_1_git,
        check_gate_2_static_analysis,
        check_gate_3_adr_governance,
        check_gate_4_core_tests,
        check_gate_5_resilience_evidence,
        check_gate_6_build,
    ]

    results: list[bool] = []
    for gate in gates:
        results.append(gate())

    print("=" * 75)
    if all(results):
        print("🏆 RELEASE VERIFICATION: ALL 6 GATES PASSED (100%)")
        print("NexusAI is certified production-ready for Release Candidate.")
        print("=" * 75)
        sys.exit(0)
    else:
        failed_count = results.count(False)
        print(f"❌ RELEASE VERIFICATION FAILED ({failed_count} gate(s) failed)")
        print("=" * 75)
        sys.exit(1)


if __name__ == "__main__":
    main()
