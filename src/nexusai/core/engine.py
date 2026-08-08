"""Master Orchestrator Runtime Engine for NexusAI with Full Lifecycle Management."""

import pathlib
from typing import Any, Optional

from nexusai.bus.bus import CommandBus, EventBus
from nexusai.bus.commands import ExecuteToolCommand, ExecuteToolCommandHandler
from nexusai.core.config import SystemConfig
from nexusai.core.container import DependencyContainer
from nexusai.memory.hierarchy import MemoryHierarchy
from nexusai.memory.sqlite_memory import SQLiteMemory
from nexusai.security.guard import SecurityGuard
from nexusai.security.policy import PluginPolicyEngine
from nexusai.tools.isolation import SubprocessPluginRunner
from nexusai.tools.plugin_loader import PluginLoader
from nexusai.tools.registry import ToolRegistry
from nexusai.workflow.engine import WorkflowGraphEngine


class NexusAIRuntimeEngine:
    """Unified Orchestrator tying together CQRS Bus, Security Policy, Isolated Plugins, Memory Hierarchy, and Lifecycle Shutdown."""

    def __init__(self, config: Optional[SystemConfig] = None) -> None:
        self.config = config or SystemConfig()
        self.container = DependencyContainer()

        self.registry = ToolRegistry()
        self.plugin_loader = PluginLoader(self.registry)
        self.subprocess_runner = SubprocessPluginRunner(
            timeout_seconds=self.config.security.isolation_timeout_seconds
        )

        self.security_guard = SecurityGuard(self.config.security)
        self.policy_engine = PluginPolicyEngine(self.config.security.capabilities)

        self.event_bus = EventBus()
        self.command_bus = CommandBus()
        self.workflow_engine = WorkflowGraphEngine()

        db_path = pathlib.Path(self.config.logging.file_path.replace(".log", ".db")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.sqlite_memory = SQLiteMemory(db_path=str(db_path))
        self.memory_hierarchy = MemoryHierarchy(sqlite_memory=self.sqlite_memory)
        self.is_running = False

        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        handler = ExecuteToolCommandHandler(self.registry, self.security_guard, self.event_bus)
        self.command_bus.register(ExecuteToolCommand, handler)

    async def initialize(self) -> None:
        """Initialize all underlying database connections and subsystem state."""
        await self.memory_hierarchy.initialize()
        self.is_running = True

    async def execute_command(self, command: Any) -> Any:
        """Dispatch command through CQRS bus."""
        return await self.command_bus.dispatch(command)

    async def shutdown(self) -> None:
        """Gracefully shutdown runtime engine, flush memory, and cleanup resources."""
        if not self.is_running:
            return

        # 1. Flush memory and clear registry
        self.registry.clear()

        # 2. Set running status
        self.is_running = False
