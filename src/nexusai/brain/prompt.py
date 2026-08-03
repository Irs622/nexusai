"""
System Prompt Engine for NexusAI with dynamic working context injection.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexusai.context.engine import WorkingContext


class PromptBuilder:
    """Generates structured system prompts for NexusAI LLM reasoning."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are NexusAI, an advanced Personal AI Operating System for macOS (Apple Silicon).\n"
        "Your mission is to assist the user by understanding natural language, automating macOS desktop workflows, "
        "executing terminal commands, and managing development tasks.\n\n"
        "Rules:\n"
        "1. You have passive environment awareness and access to native macOS tools. Always use available tools to fulfill user requests safely.\n"
        "2. Prioritize user security, privacy, and system integrity at all times.\n"
        "3. Keep your conversational responses concise, clear, and direct."
    )

    def build_system_prompt(
        self,
        persona_mode: str = "DEFAULT",
        context: "WorkingContext | None" = None,
    ) -> str:
        """Construct the system prompt for specified persona mode and inject working context."""
        prompt = self.DEFAULT_SYSTEM_PROMPT

        if context is not None:
            context_block = (
                "\n\nCURRENT WORKING CONTEXT:\n"
                f"- Active Application: {context.active_application}\n"
                f"- Active Window Title: {context.active_window_title}\n"
                f"- Git Branch: {context.git_branch or 'N/A (Not in a Git repository)'}\n"
                f"- Hardware Status: CPU {context.cpu_usage_percent:.1f}%, Memory {context.memory_usage_percent:.1f}%"
            )
            prompt += context_block

        if persona_mode == "DEVELOPER":
            prompt += (
                "\n\nMode: Developer. Focus on code structure, precise terminal commands, file line paths, and technical accuracy."
            )

        return prompt
