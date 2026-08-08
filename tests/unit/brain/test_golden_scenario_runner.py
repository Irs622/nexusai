"""Unit tests for Phase 4 P1.6 ScenarioRunner & P1.7 100 Golden Scenario Dataset."""

from __future__ import annotations

import pytest

from nexusai.brain.eval.golden_dataset import generate_golden_scenario_corpus
from nexusai.brain.eval.runner import ScenarioRunner
from nexusai.brain.eval.scenario import Scenario, ScenarioCorpus
from nexusai.brain.replay.migration import MigrationRegistry


def test_generate_100_golden_scenario_corpus():
    """Verify generate_golden_scenario_corpus() creates 100 benchmark scenarios across 5 categories."""
    corpus = generate_golden_scenario_corpus()

    assert corpus.corpus_name == "nexusai-golden-100-v1"
    assert corpus.version == 1
    assert len(corpus.scenarios) == 100

    categories = {s.category for s in corpus.scenarios}
    assert categories == {"TOOL", "RECOVERY", "PLANNING", "REFLECTION", "COMPACTION"}

    tool_scenarios = [s for s in corpus.scenarios if s.category == "TOOL"]
    recovery_scenarios = [s for s in corpus.scenarios if s.category == "RECOVERY"]
    planning_scenarios = [s for s in corpus.scenarios if s.category == "PLANNING"]
    reflection_scenarios = [s for s in corpus.scenarios if s.category == "REFLECTION"]
    compaction_scenarios = [s for s in corpus.scenarios if s.category == "COMPACTION"]

    assert len(tool_scenarios) == 20
    assert len(recovery_scenarios) == 20
    assert len(planning_scenarios) == 20
    assert len(reflection_scenarios) == 20
    assert len(compaction_scenarios) == 20


@pytest.mark.asyncio
async def test_scenario_runner_executes_corpus():
    """Verify ScenarioRunner executes a ScenarioCorpus and returns EvaluationResult reports."""
    corpus = ScenarioCorpus(
        corpus_name="unit-test-corpus",
        version=1,
        scenarios=(
            Scenario(
                scenario_id="SCENARIO-UNIT-1",
                description="Unit test scenario 1",
                user_request="Perform unit test task 1",
                category="TOOL",
            ),
            Scenario(
                scenario_id="SCENARIO-UNIT-2",
                description="Unit test scenario 2",
                user_request="Perform unit test task 2",
                category="RECOVERY",
            ),
        ),
    )

    runner = ScenarioRunner()
    results = await runner.run_corpus(corpus)

    assert len(results) == 2
    assert results[0].scenario_id == "SCENARIO-UNIT-1"
    assert results[0].success is True
    assert results[1].scenario_id == "SCENARIO-UNIT-2"
    assert results[1].success is True


def test_replay_migration_registry():
    """Verify MigrationRegistry performs schema version migration transforms."""
    registry = MigrationRegistry()

    def v1_to_v2_migration(header: dict, events: list[dict]):
        header["migrated_to_v2"] = True
        return header, events

    registry.register_migration(from_version=1, to_version=2, migration_fn=v1_to_v2_migration)

    raw_header = {"schema_version": 1, "session_id": "test-session"}
    raw_events: list[dict] = []

    migrated_header, _ = registry.migrate_log(raw_header, raw_events, target_version=2)
    assert migrated_header["schema_version"] == 2
    assert migrated_header["migrated_to_v2"] is True
