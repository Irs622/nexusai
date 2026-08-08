"""AgentRuntimeBuilder for fluent dependency injection of strategies and adapters."""

from __future__ import annotations

from typing import Callable

from nexusai.brain.loop_executor import LoopExecutor
from nexusai.brain.observation import ObservationMapper
from nexusai.brain.pipeline.pipeline import ExecutionPipeline
from nexusai.brain.ports.tool_port import IToolPort
from nexusai.brain.runtime.agent_context import AgentRuntimeContext
from nexusai.brain.service import AgentRuntimeFacade
from nexusai.brain.strategy import (
    IDecisionStrategy,
    IPlanningStrategy,
    IReflectionStrategy,
    RuleDecisionStrategy,
    RulePlanningStrategy,
    RuleReflectionStrategy,
)


class AgentRuntimeBuilder:
    """Fluent Builder constructing AgentRuntimeFacade and LoopExecutor instances via dependency injection."""

    def __init__(self) -> None:
        self._planning_strategy: IPlanningStrategy = RulePlanningStrategy()
        self._reflection_strategy: IReflectionStrategy = RuleReflectionStrategy()
        self._decision_strategy: IDecisionStrategy = RuleDecisionStrategy()
        self._tool_port: IToolPort | None = None
        self._observation_mapper: ObservationMapper = ObservationMapper()
        self._pipeline: ExecutionPipeline = ExecutionPipeline()
        self._hooks: dict[str, list[Callable[[AgentRuntimeContext], None]]] = {}

    def with_planning_strategy(self, strategy: IPlanningStrategy) -> AgentRuntimeBuilder:
        """Inject custom planning strategy implementation."""
        self._planning_strategy = strategy
        return self

    def with_reflection_strategy(self, strategy: IReflectionStrategy) -> AgentRuntimeBuilder:
        """Inject custom reflection strategy implementation."""
        self._reflection_strategy = strategy
        return self

    def with_decision_strategy(self, strategy: IDecisionStrategy) -> AgentRuntimeBuilder:
        """Inject custom decision strategy implementation."""
        self._decision_strategy = strategy
        return self

    def with_tool_port(self, tool_port: IToolPort) -> AgentRuntimeBuilder:
        """Inject tool port adapter implementation."""
        self._tool_port = tool_port
        return self

    def with_observation_mapper(self, mapper: ObservationMapper) -> AgentRuntimeBuilder:
        """Inject observation mapper implementation."""
        self._observation_mapper = mapper
        return self

    def with_pipeline(self, pipeline: ExecutionPipeline) -> AgentRuntimeBuilder:
        """Inject execution pipeline implementation."""
        self._pipeline = pipeline
        return self

    def with_hook(
        self, event_name: str, callback: Callable[[AgentRuntimeContext], None]
    ) -> AgentRuntimeBuilder:
        """Register a lifecycle hook callback."""
        if event_name not in self._hooks:
            self._hooks[event_name] = []
        self._hooks[event_name].append(callback)
        return self

    def build_executor(self) -> LoopExecutor:
        """Build configured LoopExecutor instance."""
        if self._planning_strategy is None:
            raise ValueError("Planning strategy cannot be None")
        if self._reflection_strategy is None:
            raise ValueError("Reflection strategy cannot be None")
        if self._decision_strategy is None:
            raise ValueError("Decision strategy cannot be None")
        if self._observation_mapper is None:
            raise ValueError("Observation mapper cannot be None")
        if self._pipeline is None:
            raise ValueError("Execution pipeline cannot be None")

        executor = LoopExecutor(
            planning_strategy=self._planning_strategy,
            reflection_strategy=self._reflection_strategy,
            decision_strategy=self._decision_strategy,
            tool_port=self._tool_port,
            observation_mapper=self._observation_mapper,
            pipeline=self._pipeline,
        )
        for event, callbacks in self._hooks.items():
            for cb in callbacks:
                executor.register_hook(event, cb)
        return executor

    def build(self) -> AgentRuntimeFacade:
        """Build configured AgentRuntimeFacade facade instance."""
        executor = self.build_executor()
        return AgentRuntimeFacade(loop_executor=executor, tool_port=self._tool_port)
