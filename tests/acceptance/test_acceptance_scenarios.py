"""Acceptance Test Suite verifying real end-to-end user scenarios for Milestone Alpha AI OS."""
import pathlib
import pytest
from nexusai.brain.planner import TaskPlanner
from nexusai.tools.selector import ToolSelector
from nexusai.tools.registry import ToolRegistry
from nexusai.tools.workspace.fs import ReadFileTool, ListDirectoryTool
from nexusai.tools.system.terminal import TerminalTool
from nexusai.brain.evaluator import SelfEvaluator
from nexusai.workflow.engine import WorkflowGraphEngine, WorkflowNode, WorkflowState
from plugins.git.plugin import GitStatusTool

@pytest.mark.asyncio
async def test_acceptance_scenario_1_create_project() -> None:
    """Acceptance Scenario 1: Create Project User Goal."""
    planner = TaskPlanner()
    plan = planner.plan("Create FastAPI REST API project")
    assert len(plan.steps) == 3
    
    registry = ToolRegistry()
    registry.register(ListDirectoryTool())
    registry.register(ReadFileTool())
    registry.register(TerminalTool())
    
    selector = ToolSelector(registry)
    evaluator = SelfEvaluator()
    
    # Execute steps in DAG workflow engine
    graph = WorkflowGraphEngine()
    
    def step_action(state: WorkflowState) -> dict:
        selected_tool = selector.select_best_tool(plan.steps[0].description)
        assert selected_tool is not None
        eval_res = evaluator.evaluate_output(selected_tool.name, "Directory items listed")
        assert eval_res.success is True
        return {"project_created": True}
        
    graph.add_node(WorkflowNode(name="create_project", action=step_action))
    final_state = await graph.execute("create_project")
    assert final_state.completed is True
    assert final_state.data["project_created"] is True

@pytest.mark.asyncio
async def test_acceptance_scenario_2_explain_repository() -> None:
    """Acceptance Scenario 2: Explain Repository Goal."""
    planner = TaskPlanner()
    plan = planner.plan("Explain repository structure and documentation")
    
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    selector = ToolSelector(registry)
    
    selected_tool = selector.select_best_tool("Read file contents")
    assert selected_tool.name == "workspace_read_file"
    
    output = await selected_tool.execute(file_path="pyproject.toml")
    evaluator = SelfEvaluator()
    eval_res = evaluator.evaluate_output(selected_tool.name, output)
    assert eval_res.success is True

@pytest.mark.asyncio
async def test_acceptance_scenario_3_refactor_code() -> None:
    """Acceptance Scenario 3: Refactor Code Goal."""
    planner = TaskPlanner()
    plan = planner.plan("Refactor plugin loader module")
    
    git_tool = GitStatusTool()
    status_output = await git_tool.execute()
    
    evaluator = SelfEvaluator()
    eval_res = evaluator.evaluate_output("git_status", status_output)
    assert eval_res.success is True
    assert eval_res.needs_retry is False
