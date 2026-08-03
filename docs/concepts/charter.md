---
status: stable
audience:
  - end-users
  - contributors
  - maintainers
owner:
  - core-team
applies_to:
  - project-scope
review_cycle: quarterly
last_reviewed: 2026-08-03
---

# 🎯 Project Charter

## 🎯 Purpose & Scope

The **NexusAI Project Charter** defines the explicit operational boundaries, non-goals, and measurable success metrics for the NexusAI AI Operating System.

---

## 🟢 In Scope (What We Build)

- 🤖 **Model-Agnostic LLM Routing**: Supporting local (Ollama) and cloud (OpenAI, OpenRouter, Anthropic, Gemini) models seamlessly.
- 🍏 **macOS Desktop Integration**: Deep native integration with macOS Apple Silicon, AppleScript, terminal CLI, and workspace file indexing.
- 🛝 **Zero-Trust Security Evaluator**: Permission guard, command sanitizer, and risk classifier for autonomous execution.
- 🔌 **Extensible Plugin SDK**: Clean, lightweight SDK for building custom tool plugins, providers, and memory stores.
- 💻 **Dual Interfaces**: Rich terminal CLI shell and lightweight web OS dashboard interface.

---

## 🔴 Out of Scope (What We Will NEVER Build)

- ❌ **Closed Proprietary SaaS Wrappers**: NexusAI will never require a paid cloud subscription to run core functionality.
- ❌ **Integrated Code IDE Replacement**: NexusAI is not an IDE editor (like VSCode); it integrates with existing developer environments.
- ❌ **Cloud Telemetry & User Profiling**: NexusAI will never collect or upload user files, prompts, or personal history to remote telemetry servers.
- ❌ **Cross-Platform Over-Engineering**: We focus on macOS (Apple Silicon/Intel) excellence first before attempting Windows/Linux UI ports.

---

## 📊 Quantifiable Success Metrics

To ensure NexusAI maintains high performance and engineering rigor, every release is measured against these metrics:

| Metric | Target | Current Status |
| :--- | :--- | :--- |
| **CLI Cold Start Time** | `< 1.5 seconds` | ~ 0.9s |
| **New Provider Adapter Lines of Code** | `< 100 LOC` | ~ 85 LOC |
| **Tool Execution Permission Coverage** | `100% of state-changing tools` | 100% |
| **Test Suite Execution Time** | `< 10 seconds` | ~ 4.2s |
| **Core Dependency Count** | Zero heavy binary C-extensions | Met |
