---
status: stable
audience:
  - architects
  - contributors
owner:
  - core-team
applies_to:
  - workflow-engine
review_cycle: yearly
last_reviewed: 2026-08-03
---

# Why a Cyclic Workflow Engine?

## Decision Rationale
1. **Multi-Turn Reasoning Loops**: LLMs require iterative tool execution and state evaluation loops.
2. **Vendor-Neutral Abstraction**: We utilize graph state machines (`LangGraph` currently) to decouple agent flow control from specific LLM vendors.
3. **Replacement Criteria**: If a lighter, pure-Python graph runner emerges with zero external dependencies and faster cold-start benchmarks, the engine layer can be swapped seamlessly.
