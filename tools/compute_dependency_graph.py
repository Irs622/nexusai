"""Dependency Graph SCC (Strongly Connected Components) Analyzer."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_BRAIN = PROJECT_ROOT / "src" / "nexusai" / "brain"


def get_file_module_name(file_path: Path) -> str:
    rel = file_path.relative_to(PROJECT_ROOT / "src")
    return ".".join(rel.with_suffix("").parts)


def compute_file_scc():
    # Only analyze python source files (excluding __init__.py re-export index files)
    py_files = [f for f in SRC_BRAIN.rglob("*.py") if f.name != "__init__.py"]
    modules = {get_file_module_name(f): f for f in py_files}
    graph: dict[str, set[str]] = {m: set() for m in modules}

    for mod, f in modules.items():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported = node.module

            if imported and imported.startswith("nexusai.brain"):
                for target in modules:
                    if imported == target or imported.startswith(target + "."):
                        if target != mod:
                            graph[mod].add(target)

    # Tarjan's Strongly Connected Components Algorithm
    index = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    sccs: list[list[str]] = []

    def strongconnect(v: str):
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, set()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    for v in graph:
        if v not in indices:
            strongconnect(v)

    num_nodes = len(graph)
    num_edges = sum(len(neighbors) for neighbors in graph.values())

    print("==================================================")
    print("EMPIRICAL MODULE FILE DEPENDENCY GRAPH ANALYSIS")
    print("==================================================")
    print(f"Module File Nodes : {num_nodes}")
    print(f"Module File Edges : {num_edges}")
    print(f"Strongly Connected Components (File Cycles) : {len(sccs)}")
    if sccs:
        print("Detected Module File Cycles:")
        for scc in sccs:
            print(f"  Cycle: {scc}")
    else:
        print("RESULT: 0 File Cycles Detected! Clean Module DAG.")
    print("==================================================")


if __name__ == "__main__":
    compute_file_scc()
