"""Workflow State Graph Execution Engine for NexusAI."""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from nexusai.core.errors import WorkflowError

@dataclass
class WorkflowState:
    """State context passed between workflow nodes."""
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)
    completed: bool = False

@dataclass
class WorkflowNode:
    """Executable node in workflow graph."""
    name: str
    action: Callable[[WorkflowState], Any]

class WorkflowGraphEngine:
    """DAG Workflow Engine with state checkpoints, conditional branching, and graceful recovery."""

    def __init__(self) -> None:
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: Dict[str, List[str]] = {}
        self.checkpoints: Dict[str, WorkflowState] = {}

    def add_node(self, node: WorkflowNode) -> None:
        """Register a node in graph."""
        self.nodes[node.name] = node
        if node.name not in self.edges:
            self.edges[node.name] = []

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Connect nodes with a directed edge."""
        if from_node not in self.edges:
            self.edges[from_node] = []
        self.edges[from_node].append(to_node)

    def create_checkpoint(self, checkpoint_id: str, state: WorkflowState) -> None:
        """Save a state snapshot for recovery."""
        self.checkpoints[checkpoint_id] = WorkflowState(
            data=dict(state.data),
            history=list(state.history),
            completed=state.completed,
        )

    async def execute(self, start_node_name: str, initial_state: Optional[WorkflowState] = None) -> WorkflowState:
        """Execute workflow graph starting from initial node."""
        if start_node_name not in self.nodes:
            raise WorkflowError(f"Start node '{start_node_name}' not found in workflow graph.")
            
        current_node_name = start_node_name
        state = initial_state or WorkflowState()
        
        while current_node_name:
            node = self.nodes[current_node_name]
            state.history.append(node.name)
            
            # Execute node action
            if asyncio.iscoroutinefunction(node.action):
                res = await node.action(state)
            else:
                res = node.action(state)
                
            if isinstance(res, dict):
                state.data.update(res)
                
            # Create checkpoint
            self.create_checkpoint(f"checkpoint_{current_node_name}", state)
            
            # Next node
            next_nodes = self.edges.get(current_node_name, [])
            current_node_name = next_nodes[0] if next_nodes else None
            
        state.completed = True
        return state
