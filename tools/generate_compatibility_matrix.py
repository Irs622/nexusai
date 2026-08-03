"""Automated Compatibility Matrix Generator reading provider.describe() snapshots."""

from pathlib import Path
import asyncio

from nexusai.providers import (
    MockProvider,
    ProviderCapabilities,
    ProviderRegistry,
)


async def generate_matrix() -> str:
    """Generate Markdown compatibility matrix from registered provider describe() output."""
    registry = ProviderRegistry()

    # Register current provider instances
    registry.register(MockProvider("mock_provider"))

    providers = registry.list_providers()

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
        matrix_md += (
            f"| `{p.id}` | {'✅' if caps.tools else '❌'} | "
            f"{'✅' if caps.streaming else '❌'} | "
            f"{'✅' if caps.embeddings else '❌'} | "
            f"{'✅' if caps.vision else '❌'} | "
            f"{'✅' if caps.json_mode else '❌'} | "
            f"{caps.max_context} |\n"
        )

    return matrix_md


def main() -> None:
    output_path = Path("docs/specs/extensions/compatibility_matrix.md")
    content = asyncio.run(generate_matrix())
    output_path.write_text(content)
    print(f"Updated dynamic compatibility matrix at {output_path}")


if __name__ == "__main__":
    main()
