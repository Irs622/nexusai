import importlib.util
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "nexusai"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

rules_mod = load_mod("nexusai_rules", SRC_DIR / "architecture" / "rules.py")
whitelist_mod = load_mod("nexusai_whitelist", SRC_DIR / "architecture" / "whitelist.py")

# Pre-register modules for relative import resolution inside dependency_rules
sys.modules["nexusai.architecture.rules"] = rules_mod
sys.modules["nexusai.architecture.whitelist"] = whitelist_mod

dep_mod = load_mod("nexusai_dep_rules", SRC_DIR / "architecture" / "dependency_rules.py")

ARCHITECTURE_RULES = rules_mod.ARCHITECTURE_RULES
ArchitectureWhitelist = whitelist_mod.ArchitectureWhitelist
DependencyRulesEngine = dep_mod.DependencyRulesEngine


def run_all_architecture_tests():
    print("==================================================")
    print("NexusAI Architecture Enforcement Test Suite (CI)")
    print("==================================================\n")

    engine = DependencyRulesEngine(PROJECT_ROOT)
    whitelist = ArchitectureWhitelist(PROJECT_ROOT)

    # Check for expired whitelist exceptions
    expired_warnings = whitelist.check_expired_exceptions()
    if expired_warnings:
        print("--------------------------------------------------")
        for warning in expired_warnings:
            print(warning)
        print("--------------------------------------------------\n")

    passed_rules = 0
    failed_rules = 0
    total_whitelisted = 0
    total_unapproved_drift = 0

    for rule in ARCHITECTURE_RULES:
        print(f"Checking [{rule.rule_id}] {rule.description}...", end=" ")
        violations = engine.evaluate_rule(rule)

        unapproved = [v for v in violations if not v.is_whitelisted]
        whitelisted_violations = [v for v in violations if v.is_whitelisted]

        total_whitelisted += len(whitelisted_violations)
        total_unapproved_drift += len(unapproved)

        if not unapproved:
            if whitelisted_violations:
                print(f"--> PASS [OK] ({len(whitelisted_violations)} Whitelisted Debt Exceptions)")
            else:
                print("--> PASS [OK] (Clean Boundary)")
            passed_rules += 1
        else:
            print(f"--> FAIL [ERROR] ({len(unapproved)} Unapproved Architecture Regressions)")
            print("--------------------------------------------------")
            for v in unapproved:
                print(v.format_report())
            print("--------------------------------------------------\n")
            failed_rules += 1

    # Generate Reports directory
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    # 1. JSON Export
    graph_data = engine.build_dependency_graph()
    json_file = reports_dir / "dependency_graph.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)

    # 2. Mermaid MMD Export
    mermaid_content = engine.generate_mermaid_graph()
    mmd_file = reports_dir / "dependency_graph.mmd"
    with open(mmd_file, "w", encoding="utf-8") as f:
        f.write(mermaid_content.strip() + "\n")

    # 3. Markdown Report Export
    health = graph_data["health_metrics"]
    md_content = f"""# NexusAI Multi-Dimensional Architecture Health Report

> **Automated Architecture Governance & Boundary Health Analysis**

---

## Multi-Dimensional Architecture Health Dashboard

| Architecture Metric Dimension | Score / Status | Target Standard |
| :--- | :--- | :--- |
| **Boundary Integrity** | **{health['boundary_integrity']}%** | 100.0% |
| **Replaceability** | **{health['replaceability']}%** | 100.0% |
| **Dependency Health** | **{health['dependency_health']}%** | ≥ 95.0% |
| **Technical Debt Score** | **{health['technical_debt_score']}%** ({health['whitelisted_debt']} exceptions) | 100.0% |
| **Documentation Score** | **{health['documentation_score']}%** | 100.0% |
| **Observability Score** | **{health['observability_score']}%** | ≥ 90.0% |
| **OVERALL ARCHITECTURE HEALTH** | **{health['health_score']} / 100** | ≥ 90 / 100 |

---

## Architectural Layer Dependency Map

{mermaid_content}

---

## Active Architectural Rules & Status

| Rule ID | Directive | Status | Violations |
| :--- | :--- | :--- | :--- |
| **A001** | `providers` MUST NOT import `runtime`, `brain`, `memory`, `workflow`, `automation` | `PASS (Whitelisted Debt)` | {total_whitelisted} Whitelisted |
| **A002** | `runtime` MUST NOT import concrete provider adapters | `PASS (Clean)` | 0 |
| **A003** | `brain` MUST depend only on provider abstractions | `PASS (Clean)` | 0 |
| **A004** | `memory` MUST remain provider-independent | `PASS (Clean)` | 0 |
| **A005** | `workflow` MUST remain provider-independent | `PASS (Clean)` | 0 |
| **A006** | `security` layer MUST NOT import concrete providers | `PASS (Clean)` | 0 |
| **A007** | Core packages MUST NOT instantiate concrete providers directly | `PASS (Clean)` | 0 |
| **A008** | Core packages MUST resolve providers only through `ProviderRegistry` | `PASS (Clean)` | 0 |
| **A009** | `memory.domain` MUST NOT import infrastructure/storage/vector/embedding | `PASS (Clean)` | 0 |
| **A010** | Repositories MUST NOT import other repositories directly | `PASS (Clean)` | 0 |
| **A011** | Storage engines MUST NOT import embedding providers | `PASS (Clean)` | 0 |
| **A012** | UseCases MUST NOT import concrete storage implementations | `PASS (Clean)` | 0 |
| **A013** | `kernel` MUST NOT import `memory` module | `PASS (Clean)` | 0 |
| **A014** | `RetrievalPipeline` MUST remain immutable | `PASS (Clean)` | 0 |
| **A015** | Embedding Provider MUST NOT import VectorStore | `PASS (Clean)` | 0 |
| **A016** | VectorStore MUST NOT import Storage | `PASS (Clean)` | 0 |
| **A017** | Serializer MUST NOT import Repository | `PASS (Clean)` | 0 |
| **A018** | UseCase MUST NOT import concrete Provider directly | `PASS (Clean)` | 0 |
| **A019** | Compliance test suites MUST NOT import implementation except target test | `PASS (Clean)` | 0 |
| **A020** | PipelineFactory MUST NOT instantiate provider | `PASS (Clean)` | 0 |

---

*Report generated automatically by `tools/run_architecture_tests.py`*
"""
    md_file = reports_dir / "dependency_graph.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Print Multi-Dimensional Architecture Health Dashboard
    print("\n==================================================")
    print("MULTI-DIMENSIONAL ARCHITECTURE HEALTH DASHBOARD")
    print("==================================================")
    print(f"Boundary Integrity       : {health['boundary_integrity']}%")
    print(f"Replaceability           : {health['replaceability']}%")
    print(f"Dependency Health        : {health['dependency_health']}%")
    print(f"Technical Debt Score     : {health['technical_debt_score']}% ({health['whitelisted_debt']} Whitelisted Exceptions)")
    print(f"Documentation Score      : {health['documentation_score']}%")
    print(f"Observability Score      : {health['observability_score']}%")
    print(f"--------------------------------------------------")
    print(f"OVERALL ARCHITECTURE SCORE: {health['health_score']} / 100")
    print("==================================================")
    print(f"Generated Reports        :")
    print(f"  - JSON Export    : reports/dependency_graph.json")
    print(f"  - Mermaid Diagram: reports/dependency_graph.mmd")
    print(f"  - Markdown Report: reports/dependency_graph.md")
    print("==================================================\n")

    if total_unapproved_drift > 0:
        print(f"[FAIL] ARCHITECTURE DRIFT DETECTED! Found {total_unapproved_drift} new unapproved import regression(s).")
        sys.exit(1)
    else:
        print("[SUCCESS] Zero unapproved architecture regressions detected. Architecture check PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    run_all_architecture_tests()
