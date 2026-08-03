"""Unit tests for WorkflowGraphEngine DAG execution and Engine Lifecycle Shutdown."""
import pathlib
import pytest
from nexusai.workflow.engine import WorkflowGraphEngine, WorkflowNode, WorkflowState
from nexusai.core.engine import NexusAIRuntimeEngine
from nexusai.core.config import SystemConfig
from nexusai.models.circuit_breaker import CircuitBreaker

@pytest.mark.asyncio
async def test_workflow_graph_engine_execution() -> None:
    engine = WorkflowGraphEngine()
    
    def step1(state: WorkflowState) -> dict:
        return {"step1_done": True}
        
    def step2(state: WorkflowState) -> dict:
        return {"step2_done": True}
        
    engine.add_node(WorkflowNode(name="node_1", action=step1))
    engine.add_node(WorkflowNode(name="node_2", action=step2))
    engine.add_edge("node_1", "node_2")
    
    final_state = await engine.execute("node_1")
    assert final_state.completed is True
    assert final_state.history == ["node_1", "node_2"]
    assert final_state.data["step1_done"] is True
    assert final_state.data["step2_done"] is True
    assert "checkpoint_node_1" in engine.checkpoints

@pytest.mark.asyncio
async def test_runtime_engine_lifecycle(tmp_path: pathlib.Path) -> None:
    config = SystemConfig()
    config.logging.file_path = str(tmp_path / "lifecycle.log")
    
    engine = NexusAIRuntimeEngine(config)
    await engine.initialize()
    assert engine.is_running is True
    
    await engine.shutdown()
    assert not engine.is_running
    assert len(engine.registry.get_all_tools()) == 0

def test_circuit_breaker_health_score() -> None:
    breaker = CircuitBreaker(provider_id="test_provider")
    assert breaker.calculate_health_score() == 1.0
    
    breaker.record_failure(latency_ms=500.0)
    metrics = breaker.get_metrics()
    assert "health_score" in metrics
    assert 0.0 <= metrics["health_score"] <= 1.0
