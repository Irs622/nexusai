---
status: accepted
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - model-providers
review_cycle: yearly
last_reviewed: 2026-08-03
---

# ADR 0004: Model-Agnostic Provider Abstraction

## Context
Locking NexusAI to a single LLM vendor would violate our manifesto and limit user choice.

## Decision
We enforce a strict `BaseModelProvider` interface that normalizes LLM outputs into standardized dict responses (`type: text` or `type: tool_call`).

## Consequences
- **Positive**: Enables drop-in replacement between OpenAI, Anthropic, Gemini, OpenRouter, and Ollama.
- **Negative**: Requires adapter mapping code for each provider format.
