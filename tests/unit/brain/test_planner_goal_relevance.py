"""AUDIT-18: pre-planning ranking must depend on the goal, not on catalog order."""

from __future__ import annotations

import pytest

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlannerWeights,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.planner.stages import ActionRanker, ExecutionPlanner, goal_relevance

CATALOG = ("execute_terminal", "notify", "write_file", "list_directory", "read_file", "web_fetch")


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Read the report from the filesystem", "read_file"),
        ("Show me the contents of README.md file", "read_file"),
        ("Create a new config file with dark theme", "write_file"),
        ("List every folder in the src directory", "list_directory"),
        ("Run the unit tests in the terminal", "execute_terminal"),
        ("Fetch the docs page at this URL", "web_fetch"),
    ],
)
def test_planner_selects_goal_relevant_tool(goal: str, expected: str) -> None:
    ctx = PlanningContext(
        goal_component=PlanningGoal(goal=AgentGoal(description=goal)),
        resources_component=PlanningResources(available_tools=CATALOG),
    )
    _, trace = ExecutionPlanner().plan(ctx)
    assert trace.outcome.chosen_action == expected


def test_relevant_tool_scores_higher_than_unrelated() -> None:
    ranker = ActionRanker()
    weights = PlannerWeights()
    goal = "Read the changelog file"
    relevant = ranker.score_candidate("read_file", weights, goal_description=goal)
    unrelated = ranker.score_candidate("notify", weights, goal_description=goal)
    assert relevant.score > unrelated.score


def test_without_goal_scoring_is_unchanged() -> None:
    ranker = ActionRanker()
    weights = PlannerWeights()
    assert (
        ranker.score_candidate("read_file", weights).score
        == ranker.score_candidate("notify", weights).score
    )


def test_goal_relevance_bounds() -> None:
    assert goal_relevance("read the file", "read_file") == 1.0
    assert goal_relevance("read the notes", "read_file") == 0.5
    assert goal_relevance("ping the team", "read_file") == 0.0
    assert goal_relevance("anything", "") == 0.0
