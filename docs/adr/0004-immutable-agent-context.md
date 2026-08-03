# ADR 0004: Immutable AgentContext and Reducer Pattern

- **Status**: Accepted
- **Date**: 2026-08-03
- **Authors**: NexusAI Core Team

## Context & Problem Statement
Direct mutation of execution state across multiple runtime components leads to subtle state corruption, difficult debugging, and parameter instability.

## Decision Drivers
- State predictability and auditability.
- Multi-threaded and asynchronous safety.
- Easy session persistence, state restoration, and replayability.

## Considered Options
1. Mutable shared dataclass instance.
2. Immutable dataclass with `.update()` functional state reducer.

## Decision Outcome
Chosen Option: **Option 2 (Immutable dataclass with reducer)**.
`AgentContext` is frozen and can only produce new state snapshots via `context.update(...)`.
