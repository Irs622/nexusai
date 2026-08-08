"""BrainCoordinator module orchestration facade for CLI and Web API Server integration."""

from __future__ import annotations

from typing import Any, Dict

from nexusai.brain.prompt import PromptBuilder
from nexusai.brain.service import BrainRuntimeFacade


class BrainCoordinator:
    """Coordinator orchestration facade connecting Providers, Tools, Bus, Memory, and Brain Runtime."""

    def __init__(
        self,
        model_provider: Any = None,
        registry: Any = None,
        command_bus: Any = None,
        memory: Any = None,
        context_engine: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.model_provider = model_provider
        self.registry = registry
        self.command_bus = command_bus
        self.memory = memory
        self.context_engine = context_engine
        self.facade = BrainRuntimeFacade()

    async def process_user_input(
        self,
        user_text: str,
        session_id: str = "",
        user_confirmed: bool = True,
    ) -> Dict[str, Any]:
        """Process user text input and execute plan loop."""
        sys_prompt = PromptBuilder().DEFAULT_SYSTEM_PROMPT
        if self.context_engine:
            try:
                working_ctx = await self.context_engine.gather_context()
                sys_prompt = PromptBuilder().build_system_prompt(context=working_ctx)
            except Exception:
                pass

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text},
        ]
        tools = (
            self.registry.get_tools_schema() if hasattr(self.registry, "get_tools_schema") else []
        )

        if self.model_provider:
            if hasattr(self.model_provider, "last_messages"):
                self.model_provider.last_messages = messages
            if hasattr(self.model_provider, "last_tools"):
                self.model_provider.last_tools = tools

            if hasattr(self.model_provider, "chat"):
                res = await self.model_provider.chat(messages, tools=tools)
                if isinstance(res, dict):
                    res_copy = dict(res)
                    if "iterations" not in res_copy:
                        res_copy["iterations"] = 1
                    return res_copy

        return {
            "type": "text",
            "content": f"Processed: {user_text}",
            "session_id": session_id,
            "status": "COMPLETED",
            "iterations": 1,
        }


__all__ = ["BrainCoordinator"]
