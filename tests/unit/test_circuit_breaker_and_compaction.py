"""Unit tests for CircuitBreaker state transitions and Memory Compaction."""
import time
import pathlib
import pytest
from nexusai.models.circuit_breaker import CircuitBreaker, CircuitState
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.memory.hierarchy import MemoryHierarchy

def test_circuit_breaker_state_transitions() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0.2)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True
    
    # 1. First failure
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    
    # 2. Second failure trips to OPEN
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.can_execute() is False
    
    # 3. Wait recovery timeout -> transitions to HALF_OPEN
    time.sleep(0.25)
    assert breaker.can_execute() is True
    assert breaker.state == CircuitState.HALF_OPEN
    
    # 4. Success resets to CLOSED
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

@pytest.mark.asyncio
async def test_memory_compaction(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "compact_test.db")
    sqlite_mem = SQLiteMemory(db_path=db_path)
    hierarchy = MemoryHierarchy(sqlite_memory=sqlite_mem)
    await hierarchy.initialize()
    
    for i in range(15):
        await hierarchy.record_interaction("sess_comp", "user", f"Message turn {i}")
        
    summary = await hierarchy.compact_history("sess_comp", max_turns=5)
    assert "Compacted Summary" in summary
