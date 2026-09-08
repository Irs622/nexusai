"""Automated Compatibility Matrix Generator reading provider.describe() snapshots."""

import asyncio
from pathlib import Path

from nexusai.providers import (
    Capability,
    MockProvider,
    ProviderRegistry,
)


async def generate_matrix() -> str:
    """Generate Markdown compatibility matrix from registered provider describe() output."""
    registry = ProviderRegistry()

    # Register current provider instances
    registry.register(MockProvider("mock_provider"))

    providers = [registry.get(pid) for pid in registry.list_provider_ids()]

    matrix_md = """---
status: stable
audience:
  - architects
  - core-developers
owner:
  - core-team
applies_to:
  - provider-adapters
review_cycle: quarterly
last_reviewed: 2026-08-04
---

# 📊 Dynamic Provider Compatibility & Capability Matrix

*Automated matrix generated directly from provider `describe()` capability snapshots.*

| Provider ID | Tools | Streaming | Embeddings | Vision | JSON Mode | Max Context |
|---|---|---|---|---|---|---|
"""
    for p in providers:
        caps = await p.describe()
        models = await p.list_models()
        max_ctx = models[0].context_window if models else "N/A"
        matrix_md += (
            f"| `{p.id}` | {'✅' if caps.supports(Capability.TOOLS) else '❌'} | "
            f"{'✅' if caps.supports(Capability.STREAMING) else '❌'} | "
            f"{'✅' if caps.supports(Capability.EMBEDDINGS) else '❌'} | "
            f"{'✅' if caps.supports(Capability.VISION) else '❌'} | "
            f"{'✅' if caps.supports(Capability.JSON_MODE) else '❌'} | "
            f"{max_ctx} |\n"
        )

    return matrix_md


def main() -> None:
    output_path = Path("docs/specs/extensions/compatibility_matrix.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = asyncio.run(generate_matrix())
    output_path.write_text(content, encoding="utf-8")
    print(f"Updated dynamic compatibility matrix at {output_path}")


if __name__ == "__main__":
    main()
