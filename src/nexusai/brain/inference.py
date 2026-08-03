"""InferenceService Indirection Layer."""
from typing import Dict, Any, Optional
from nexusai.models.base import BaseModelProvider
from nexusai.models.router import ProviderRouter

class InferenceService:
    """Portable LLM inference abstraction insulating ReasoningEngine from provider implementations."""

    def __init__(self, router: Optional[ProviderRouter] = None) -> None:
        self.router = router

    async def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        """Generate response via routed LLM provider or fallback."""
        if self.router:
            pid, provider = self.router.select_best_provider()
            return await provider.generate(prompt=prompt, system_prompt=system_prompt)
            
        return f"Inference response for: {prompt[:50]}"
