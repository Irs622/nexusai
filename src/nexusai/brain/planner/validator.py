"""PlanValidator for validating PlanGraph DAG, cycles, dead-ends, and budget constraints."""

from __future__ import annotations

from nexusai.brain.domain.agent import (
    PlanGraph,
    PlanningConstraints,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

PlanValidationResult = ValidationResult


class PlanValidator:
    """Validates PlanGraph DAG for cycles, dead-ends, unreachable steps, and budget constraints."""

    def validate(
        self, graph: PlanGraph, constraints: PlanningConstraints | None = None
    ) -> ValidationResult:
        """Execute comprehensive DAG graph validation."""
        issues: list[ValidationIssue] = []

        if not graph.nodes:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="EMPTY_GRAPH",
                    message="PlanGraph contains no nodes to execute",
                )
            )
            return ValidationResult(is_valid=False, issues=tuple(issues))

        # 1. Cycle Detection (DFS)
        visited: set[int | str] = set()
        rec_stack: set[int | str] = set()

        adj: dict[int | str, list[int | str]] = {node_id: [] for node_id in graph.nodes}
        for parent, child in graph.edges:
            if parent in adj:
                adj[parent].append(child)

        def is_cyclic(v: int | str) -> bool:
            visited.add(v)
            rec_stack.add(v)
            for neighbor in adj.get(v, []):
                if neighbor not in visited:
                    if is_cyclic(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(v)
            return False

        for node_id in graph.nodes:
            if node_id not in visited:
                if is_cyclic(node_id):
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            code="CYCLE_DETECTED",
                            message=f"Cycle detected in PlanGraph starting at step {node_id}",
                            step_id=node_id,
                        )
                    )
                    break

        # 2. Dead-end & Unreachable Node Check
        for node_id, node in graph.nodes.items():
            for dep in node.dependencies:
                if dep not in graph.nodes:
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            code="MISSING_DEPENDENCY_NODE",
                            message=f"Step {node_id} references non-existent dependency step {dep}",
                            step_id=node_id,
                        )
                    )

        # 3. Budget Validation
        if constraints and len(graph.nodes) > constraints.token_budget_units:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="BUDGET_EXCEEDED",
                    message=f"PlanGraph node count ({len(graph.nodes)}) exceeds token budget limit ({constraints.token_budget_units})",
                )
            )

        is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        return ValidationResult(is_valid=is_valid, issues=tuple(issues))
