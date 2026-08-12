"""Structured planning output container decoupling model response parsing from engine execution."""

from __future__ import annotations

from dataclasses import dataclass
from nexusai.brain.domain.agent import PlanGraph


@dataclass(frozen=True)
class PlanningOutput:
    """Immutable domain representation of a parsed planning output."""

    plan_graph: PlanGraph
    reasoning_summary: str | None = None
