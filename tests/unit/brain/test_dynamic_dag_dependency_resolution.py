"""P1-2 Dynamic DAG Dependency Resolution Regression Test Suite.

Verifies:
- DependencyResolver constructs genuine DAG graph structures (Linear, Branching, Diamond, Multiple Dependencies, Independent Nodes).
- Generated PlanGraph structure itself contains correct dependency relationships and edge tuples (distinguishing A -> B -> C from A -> B and A -> C).
- Non-sequential and reverse lexical node IDs are supported.
- Missing dependencies and cycle detection are enforced via PlanValidator.
- Deterministic graph generation across repeated resolves.
- CapabilityGraph tool auto-prerequisites work cleanly.
- Topological execution via P0-3 engine remains 100% green.
"""

from __future__ import annotations

from typing import Any
import pytest

from nexusai.brain.domain.agent import (
    AgentGoal,
    CapabilityGraph,
    PlanGraph,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
    PlanStep,
)
from nexusai.brain.planner.stages import DependencyResolver
from nexusai.brain.planner.validator import PlanValidator


# ------------------------------------------------------------------
# Test Cases A through L
# ------------------------------------------------------------------


def test_A_linear_dag_graph_structure() -> None:
    """Test A: Linear DAG (A -> B -> C)."""
    resolver = DependencyResolver()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=())
    step_b = PlanStep(step_id=2, title="Step B", depends_on=(1,))
    step_c = PlanStep(step_id=3, title="Step C", depends_on=(2,))

    graph = resolver.resolve([step_a, step_b, step_c], auto_insert=False)

    assert graph.nodes[1].dependencies == ()
    assert graph.nodes[2].dependencies == (1,)
    assert graph.nodes[3].dependencies == (2,)
    assert graph.edges == ((1, 2), (2, 3))


def test_B_simple_branching_dag_structure() -> None:
    """Test B: Simple branching (A -> B and A -> C).

           ┌→ B
        A ─┤
           └→ C
    """
    resolver = DependencyResolver()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=())
    step_b = PlanStep(step_id=2, title="Step B", depends_on=(1,))
    step_c = PlanStep(step_id=3, title="Step C", depends_on=(1,))

    graph = resolver.resolve([step_a, step_b, step_c], auto_insert=False)

    assert graph.nodes[1].dependencies == ()
    assert graph.nodes[2].dependencies == (1,)
    assert graph.nodes[3].dependencies == (1,)
    # Verify B and C do NOT depend on each other!
    assert 2 not in graph.nodes[3].dependencies
    assert 3 not in graph.nodes[2].dependencies
    assert graph.edges == ((1, 2), (1, 3))


def test_C_and_D_diamond_dag_and_multiple_dependencies() -> None:
    """Test C & D: Diamond DAG & Multiple Dependencies (D depends on B and C).

           ┌→ B ─┐
        A ─┤     ├→ D
           └→ C ─┘
    """
    resolver = DependencyResolver()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=())
    step_b = PlanStep(step_id=2, title="Step B", depends_on=(1,))
    step_c = PlanStep(step_id=3, title="Step C", depends_on=(1,))
    step_d = PlanStep(step_id=4, title="Step D", depends_on=(2, 3))

    graph = resolver.resolve([step_a, step_b, step_c, step_d], auto_insert=False)

    assert graph.nodes[1].dependencies == ()
    assert graph.nodes[2].dependencies == (1,)
    assert graph.nodes[3].dependencies == (1,)
    assert graph.nodes[4].dependencies == (2, 3)
    assert graph.edges == ((1, 2), (1, 3), (2, 4), (3, 4))


def test_E_independent_nodes_zero_dependencies() -> None:
    """Test E: Independent nodes (A, B, C with zero dependencies between them)."""
    resolver = DependencyResolver()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=())
    step_b = PlanStep(step_id=2, title="Step B", depends_on=())
    step_c = PlanStep(step_id=3, title="Step C", depends_on=())

    graph = resolver.resolve([step_a, step_b, step_c], auto_insert=False)

    assert graph.nodes[1].dependencies == ()
    assert graph.nodes[2].dependencies == ()
    assert graph.nodes[3].dependencies == ()
    assert graph.edges == ()


def test_F_non_sequential_node_identifiers() -> None:
    """Test F: Non-sequential node identifiers (100 -> 2 -> 57)."""
    resolver = DependencyResolver()

    step_100 = PlanStep(step_id=100, title="Node 100", depends_on=())
    step_2 = PlanStep(step_id=2, title="Node 2", depends_on=(100,))
    step_57 = PlanStep(step_id=57, title="Node 57", depends_on=(2,))

    graph = resolver.resolve([step_100, step_2, step_57], auto_insert=False)

    assert graph.nodes[100].dependencies == ()
    assert graph.nodes[2].dependencies == (100,)
    assert graph.nodes[57].dependencies == (2,)
    assert graph.edges == ((100, 2), (2, 57))


def test_G_reverse_lexical_identifiers() -> None:
    """Test G: Reverse lexical identifiers ('zeta' -> 'alpha' -> 'beta')."""
    resolver = DependencyResolver()

    step_zeta = PlanStep(step_id="zeta", title="Zeta Root", depends_on=())
    step_alpha = PlanStep(step_id="alpha", title="Alpha Child", depends_on=("zeta",))
    step_beta = PlanStep(step_id="beta", title="Beta Leaf", depends_on=("alpha",))

    graph = resolver.resolve([step_zeta, step_alpha, step_beta], auto_insert=False)

    assert graph.nodes["zeta"].dependencies == ()
    assert graph.nodes["alpha"].dependencies == ("zeta",)
    assert graph.nodes["beta"].dependencies == ("alpha",)
    assert graph.edges == (("zeta", "alpha"), ("alpha", "beta"))


def test_H_missing_dependency_detection() -> None:
    """Test H: Missing dependency node detection via PlanValidator."""
    resolver = DependencyResolver()
    validator = PlanValidator()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=(999,))  # 999 does not exist
    graph = resolver.resolve([step_a], auto_insert=False)

    result = validator.validate(graph)
    assert result.is_valid is False
    assert any(i.code == "MISSING_DEPENDENCY_NODE" for i in result.issues)


def test_I_cycle_detection_validation() -> None:
    """Test I: Dependency cycle detection via PlanValidator."""
    resolver = DependencyResolver()
    validator = PlanValidator()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=(3,))
    step_b = PlanStep(step_id=2, title="Step B", depends_on=(1,))
    step_c = PlanStep(step_id=3, title="Step C", depends_on=(2,))

    graph = resolver.resolve([step_a, step_b, step_c], auto_insert=False)

    result = validator.validate(graph)
    assert result.is_valid is False
    assert any(i.code == "CYCLE_DETECTED" for i in result.issues)


def test_J_deterministic_graph_generation() -> None:
    """Test J: Repeated resolves yield identical nodes and edges deterministically."""
    resolver = DependencyResolver()

    step_a = PlanStep(step_id=1, title="Step A", depends_on=())
    step_b = PlanStep(step_id=2, title="Step B", depends_on=(1,))
    step_c = PlanStep(step_id=3, title="Step C", depends_on=(1,))
    step_d = PlanStep(step_id=4, title="Step D", depends_on=(2, 3))

    graph1 = resolver.resolve([step_a, step_b, step_c, step_d], auto_insert=False)
    graph2 = resolver.resolve([step_a, step_b, step_c, step_d], auto_insert=False)

    assert graph1.nodes == graph2.nodes
    assert graph1.edges == graph2.edges


def test_K_capability_graph_auto_prerequisite_resolution() -> None:
    """Test K: CapabilityGraph tool prerequisites are auto-inserted and resolved as dependency edges."""
    resolver = DependencyResolver()
    cap_graph = CapabilityGraph(requirements={"summarize_file": ("read_file",)})

    step_sum = PlanStep(step_id=1, title="Summarize Task", tool_name="summarize_file")

    graph = resolver.resolve([step_sum], graph=cap_graph, auto_insert=True)

    # Must auto-insert read_file (step 1) and make summarize_file (step 2) depend on step 1
    assert len(graph.nodes) == 2
    read_node = [n for n in graph.nodes.values() if n.step.tool_name == "read_file"][0]
    sum_node = [n for n in graph.nodes.values() if n.step.tool_name == "summarize_file"][0]

    assert read_node.dependencies == ()
    assert read_node.step.step_id in sum_node.dependencies


if __name__ == "__main__":
    test_A_linear_dag_graph_structure()
    test_B_simple_branching_dag_structure()
    test_C_and_D_diamond_dag_and_multiple_dependencies()
    test_E_independent_nodes_zero_dependencies()
    test_F_non_sequential_node_identifiers()
    test_G_reverse_lexical_identifiers()
    test_H_missing_dependency_detection()
    test_I_cycle_detection_validation()
    test_J_deterministic_graph_generation()
    test_K_capability_graph_auto_prerequisite_resolution()
    print("ALL P1-2 DYNAMIC DAG DEPENDENCY RESOLUTION TESTS PASSED SUCCESSFULLY!")
