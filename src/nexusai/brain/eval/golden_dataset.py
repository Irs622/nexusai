"""Phase 4 P1.7 Golden Scenario Dataset Generator (100 Scenarios)."""

from __future__ import annotations

from nexusai.brain.eval.scenario import Scenario, ScenarioCorpus


def generate_golden_scenario_corpus() -> ScenarioCorpus:
    """Generate canonical 100-scenario Golden Benchmark Dataset across 5 core categories."""
    scenarios: list[Scenario] = []

    # Category 1: Tool Execution Success (Scenarios 001 - 020)
    for i in range(1, 21):
        scenarios.append(
            Scenario(
                scenario_id=f"TOOL-{i:03d}",
                description=f"Execute tool operation scenario #{i}",
                user_request=f"Perform tool execution task #{i}",
                category="TOOL",
                difficulty="EASY" if i <= 10 else "MEDIUM",
                tags=("tool", "execution", f"task-{i}"),
                expected_tools=(f"workspace_tool_{i % 5}",),
                expected_decision="COMPLETE",
            )
        )

    # Category 2: Failure & Recovery (Scenarios 021 - 040)
    for i in range(21, 41):
        scenarios.append(
            Scenario(
                scenario_id=f"RECOVERY-{i:03d}",
                description=f"Handle tool failure and recover execution scenario #{i}",
                user_request=f"Perform resilient operation #{i}",
                category="RECOVERY",
                difficulty="MEDIUM" if i <= 30 else "HARD",
                tags=("failure", "recovery", "retry", f"task-{i}"),
                expected_tools=(f"retryable_tool_{i % 4}",),
                expected_decision="COMPLETE",
            )
        )

    # Category 3: Planning & Re-planning (Scenarios 041 - 060)
    for i in range(41, 61):
        scenarios.append(
            Scenario(
                scenario_id=f"PLANNING-{i:03d}",
                description=f"Decompose multi-step plan scenario #{i}",
                user_request=f"Plan and execute goal #{i}",
                category="PLANNING",
                difficulty="MEDIUM",
                tags=("planning", "steps", f"task-{i}"),
                expected_tools=("planner_tool",),
                expected_decision="COMPLETE",
            )
        )

    # Category 4: Reflection & Analysis (Scenarios 061 - 080)
    for i in range(61, 81):
        scenarios.append(
            Scenario(
                scenario_id=f"REFLECTION-{i:03d}",
                description=f"Perform state reflection and failure analysis scenario #{i}",
                user_request=f"Analyze state and reflect on goal #{i}",
                category="REFLECTION",
                difficulty="MEDIUM",
                tags=("reflection", "analysis", f"task-{i}"),
                expected_tools=("analyzer_tool",),
                expected_decision="COMPLETE",
            )
        )

    # Category 5: Context Compaction & Summarization (Scenarios 081 - 100)
    for i in range(81, 101):
        scenarios.append(
            Scenario(
                scenario_id=f"COMPACTION-{i:03d}",
                description=f"Execute context compaction on large observation payload scenario #{i}",
                user_request=f"Process large context payload task #{i}",
                category="COMPACTION",
                difficulty="HARD",
                tags=("compaction", "budget", "summary", f"task-{i}"),
                expected_tools=("large_data_tool",),
                expected_decision="COMPLETE",
            )
        )

    return ScenarioCorpus(
        corpus_name="nexusai-golden-100-v1",
        version=1,
        generator="NexusAI Golden Dataset Generator",
        scenarios=tuple(scenarios),
    )
