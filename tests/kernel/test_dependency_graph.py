"""
Unit tests for RuntimeDependencyGraph.
"""

import pytest

from nexusai.core.errors import DependencyCycleError, GraphFrozenError, MissingDependencyError
from nexusai.kernel.contracts import ServiceDescriptor
from nexusai.kernel.dependency_graph import RuntimeDependencyGraph


def test_dependency_graph_topological_boot_and_shutdown_order():
    graph = RuntimeDependencyGraph()

    # Kernel -> DB -> Memory -> Agent
    desc_db = ServiceDescriptor(id="db", name="Database", version="1.0.0")
    desc_mem = ServiceDescriptor(id="mem", name="Memory", version="1.0.0", dependencies=("db",))
    desc_agent = ServiceDescriptor(id="agent", name="Agent", version="1.0.0", dependencies=("mem",))

    graph.add_service(desc_agent)
    graph.add_service(desc_db)
    graph.add_service(desc_mem)

    boot_order = graph.get_startup_order()
    assert boot_order == ("db", "mem", "agent")

    shutdown_order = graph.get_shutdown_order()
    assert shutdown_order == ("agent", "mem", "db")


def test_dependency_graph_missing_dependency():
    graph = RuntimeDependencyGraph()
    desc_mem = ServiceDescriptor(id="mem", name="Memory", version="1.0.0", dependencies=("missing_db",))
    graph.add_service(desc_mem)

    with pytest.raises(MissingDependencyError) as exc_info:
        graph.validate()
    assert "missing_db" in str(exc_info.value)


def test_dependency_graph_circular_dependency():
    graph = RuntimeDependencyGraph()
    # A depends on B, B depends on A
    desc_a = ServiceDescriptor(id="srv_a", name="A", version="1.0.0", dependencies=("srv_b",))
    desc_b = ServiceDescriptor(id="srv_b", name="B", version="1.0.0", dependencies=("srv_a",))

    graph.add_service(desc_a)
    graph.add_service(desc_b)

    with pytest.raises(DependencyCycleError):
        graph.get_startup_order()


def test_dependency_graph_freezing():
    graph = RuntimeDependencyGraph()
    desc_db = ServiceDescriptor(id="db", name="DB", version="1.0.0")
    graph.add_service(desc_db)

    assert graph.is_frozen is False
    graph.freeze()
    assert graph.is_frozen is True

    # Modifying frozen graph raises error
    desc_extra = ServiceDescriptor(id="extra", name="Extra", version="1.0.0")
    with pytest.raises(GraphFrozenError):
        graph.add_service(desc_extra)
