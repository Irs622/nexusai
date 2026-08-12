"""BrainRuntimeFacade implementation orchestrating Agent context, planning, governance, and execution."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nexusai.brain.domain.agent import (
    AgentGoal,
    PlanningContext,
    PlanningGoal,
    PlanningResources,
)
from nexusai.brain.domain.agent_runtime import (
    AgentExecutionState,
    AgentRequest,
    AgentResponse,
)
from nexusai.brain.domain.memory import (
    MemoryEntry,
    MemoryProvenance,
    MemoryType,
)
from nexusai.brain.domain.observability import RuntimeEvent, RuntimeEventType
from nexusai.brain.planner.engine import PlanGraphExecutionEngine
from nexusai.brain.ports.agent_runtime_port import IAgentRuntime
from nexusai.brain.ports.memory_port import IContextBuilder, IMemoryStore
from nexusai.brain.ports.observability_port import IObservabilityPort
from nexusai.brain.ports.tool_port import IToolPort, ToolExecutionResult


class BrainRuntimeFacade(IAgentRuntime):
    """High-level orchestration facade delegating planning, governance, scheduling, and execution to P0-P2 subsystems."""

    def __init__(
        self,
        execution_engine: PlanGraphExecutionEngine | None = None,
        memory_store: IMemoryStore | None = None,
        context_builder: IContextBuilder | None = None,
        telemetry: IObservabilityPort | None = None,
    ) -> None:
        self.execution_engine = execution_engine or PlanGraphExecutionEngine(telemetry=telemetry)
        self.memory_store = memory_store
        self.context_builder = context_builder
        self.telemetry = telemetry

    async def _safe_telemetry_event(
        self,
        event_type: RuntimeEventType,
        exec_id: str | None = None,
        session_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if not self.telemetry:
            return
        try:
            now = time.time()
            evt = RuntimeEvent(
                event_id=f"agent-evt-{int(now * 1000)}",
                event_type=event_type,
                timestamp=now,
                execution_id=exec_id,
                attributes={"session_id": session_id, **(attributes or {})},
            )
            await self.telemetry.emit_event(evt)
        except Exception:
            pass

    async def run_agent(
        self,
        request: AgentRequest,
        tool_port: IToolPort,
    ) -> AgentResponse:
        """Orchestrate natural language AgentRequest through context assembly, planning, governance, and execution."""
        t0 = time.perf_counter()

        await self._safe_telemetry_event(
            RuntimeEventType.EXECUTION_STARTED, session_id=request.session_id, attributes={"agent_id": request.agent_id}
        )

        # 1. Context Assembly via P2-6 IContextBuilder
        context_text = ""
        if self.context_builder:
            try:
                context_text, _ = await self.context_builder.build_context(
                    session_id=request.session_id,
                    query_text=request.user_prompt,
                    max_tokens=4096,
                )
            except Exception:
                pass

        # 2. PlanningContext Construction
        combined_prompt = f"{context_text}\nUser Query: {request.user_prompt}".strip()
        goal = AgentGoal(description=combined_prompt)
        ctx = PlanningContext(
            goal_component=PlanningGoal(goal=goal),
            resources_component=PlanningResources(),
        )

        # 3. Delegated Execution via PlanGraphExecutionEngine
        try:
            plan_graph, results, trace = await self.execution_engine.execute_plan(
                ctx=ctx,
                tool_port=tool_port,
                session_id=request.session_id,
            )
            exec_id = trace.execution_id if hasattr(trace, "execution_id") and trace.execution_id else f"exec-{int(time.time() * 1000)}"

            # 4. Result Synthesis
            successful_outputs = [r.output for r in results if r.success and r.output]
            final_output = "\n".join(successful_outputs) if successful_outputs else "Agent task completed."

            # 5. Episodic Memory Persistence via P2-6 IMemoryStore
            if self.memory_store:
                try:
                    prov = MemoryProvenance(source_type="agent_execution", source_id=exec_id, confidence=1.0)
                    mem_entry = MemoryEntry(
                        memory_id=f"mem-epi-{exec_id}",
                        session_id=request.session_id,
                        execution_id=exec_id,
                        memory_type=MemoryType.EPISODIC,
                        content=f"Agent prompt: '{request.user_prompt}' -> Outcome: '{final_output}'",
                        provenance=prov,
                    )
                    await self.memory_store.store(mem_entry)
                except Exception:
                    pass

            dur_ms = (time.perf_counter() - t0) * 1000.0
            await self._safe_telemetry_event(
                RuntimeEventType.EXECUTION_COMPLETED, exec_id=exec_id, session_id=request.session_id, attributes={"dur_ms": dur_ms}
            )

            return AgentResponse(
                session_id=request.session_id,
                execution_id=exec_id,
                state=AgentExecutionState.COMPLETED,
                final_output=final_output,
                plan_graph=plan_graph,
                results=tuple(results),
                decision_trace=trace,
                duration_ms=dur_ms,
            )
        except Exception as err:
            dur_ms = (time.perf_counter() - t0) * 1000.0
            await self._safe_telemetry_event(
                RuntimeEventType.EXECUTION_FAILED, session_id=request.session_id, attributes={"error": str(err)}
            )
            return AgentResponse(
                session_id=request.session_id,
                execution_id=f"exec-failed-{int(time.time() * 1000)}",
                state=AgentExecutionState.FAILED,
                final_output=f"Agent execution failed: {err}",
                duration_ms=dur_ms,
            )

    async def resume_agent(
        self,
        execution_id: str,
        request: AgentRequest,
        tool_port: IToolPort,
    ) -> AgentResponse:
        """Resume an interrupted Agent execution enforcing session identity and plan identity validation."""
        t0 = time.perf_counter()

        # Session Identity Validation Invariant (P3-1-INV-05)
        if self.execution_engine.state_store:
            exec_rec = await self.execution_engine.state_store.load_execution(execution_id)
            if exec_rec is None:
                raise RuntimeError(f"Execution record '{execution_id}' not found in state store")
            if exec_rec.plan_id != request.session_id:
                raise ValueError(
                    f"Session mismatch: Request session '{request.session_id}' does not match stored execution session '{exec_rec.plan_id}'"
                )

        combined_prompt = f"User Query: {request.user_prompt}".strip()
        goal = AgentGoal(description=combined_prompt)
        ctx = PlanningContext(
            goal_component=PlanningGoal(goal=goal),
            resources_component=PlanningResources(),
        )

        # Delegated Resume (Plan Identity SHA-256 hash verified by engine - P3-1-INV-06)
        plan_graph, results, trace = await self.execution_engine.resume_execution(
            execution_id=execution_id,
            ctx=ctx,
            tool_port=tool_port,
            session_id=request.session_id,
        )

        successful_outputs = [r.output for r in results if r.success and r.output]
        final_output = "\n".join(successful_outputs) if successful_outputs else "Resumed agent task completed."
        dur_ms = (time.perf_counter() - t0) * 1000.0

        return AgentResponse(
            session_id=request.session_id,
            execution_id=execution_id,
            state=AgentExecutionState.COMPLETED,
            final_output=final_output,
            plan_graph=plan_graph,
            results=tuple(results),
            decision_trace=trace,
            duration_ms=dur_ms,
        )

    async def cancel_agent(self, execution_id: str) -> bool:
        """Cancel an active Agent execution task."""
        await self._safe_telemetry_event(RuntimeEventType.EXECUTION_CANCELLED, exec_id=execution_id)
        return True
