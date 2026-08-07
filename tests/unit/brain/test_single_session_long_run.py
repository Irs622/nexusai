"""Single-Session Memory Stress Benchmark — 10,000 Turn Observation Accumulation Test.

Verifies that in a long single session accumulating 10,000 observations,
Context Compaction maintains bounded memory growth (< 1.0 MB delta) and prevents memory bloat.
"""

from __future__ import annotations

import asyncio
import gc
import tracemalloc
from uuid import uuid4

from nexusai.brain.builder import AgentRuntimeBuilder
from nexusai.brain.compaction.budget import ContextBudget
from nexusai.brain.compaction.importance import RetentionPolicy
from nexusai.brain.container import RuntimeDependencies
from nexusai.brain.domain.agent import AgentGoal
from nexusai.brain.domain.session import BrainSession
from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.runtime.state import SessionState


async def test_single_session_10k_observations():
    """Verify single-session observation compaction over 10,000 iterations in one WorkingMemory instance."""
    budget = ContextBudget(max_units=1000, warning_threshold_ratio=0.5)
    policy = RetentionPolicy(max_active_observations=10, preserve_artifacts=True)

    deps = RuntimeDependencies(
        context_budget=budget,
        retention_policy=policy,
    )
    executor = LoopExecutor(deps=deps)
    facade = AgentRuntimeBuilder().build()
    facade._executor = executor

    session = BrainSession(session_id=uuid4(), conversation_id=uuid4())
    goal = AgentGoal(description="Single session 10,000 turn benchmark goal")
    state = SessionState(provider_id="mock", active_model="mock-v1")

    agent_ctx = facade.create_agent_context(session=session, goal=goal, state=state)
    mem = agent_ctx.working_memory

    gc.collect()
    tracemalloc.start()
    mem_samples: list[float] = []

    # Run 10,000 iterations in chunks of 1,000 accumulating in single WorkingMemory instance
    for chunk in range(10):
        for idx in range(1000):
            await executor.execute_loop(agent_ctx)

        gc.collect()
        curr, peak = tracemalloc.get_traced_memory()
        mem_samples.append(round(curr / 1024.0, 2))

    tracemalloc.stop()

    print(f"Memory samples across 10,000 single-session turns (KB): {mem_samples}")
    delta_kb = mem_samples[-1] - mem_samples[0]
    print(f"Total single-session memory delta across 10,000 turns: {delta_kb:.2f} KB")

    # Bounded observation count invariant
    assert len(mem.observations) <= 20, f"Observation count bloat detected: {len(mem.observations)} > 20"

    # Bounded memory growth delta invariant (< 1000 KB / 1.0 MB)
    assert delta_kb < 1000.0, f"Memory leak detected: grew by {delta_kb:.2f} KB!"
    print("10,000 SINGLE-SESSION TURN BENCHMARK COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_single_session_10k_observations())
