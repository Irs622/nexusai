# 13. Model Context Protocol (MCP) Client & Tool Adapter Integration

- **Status**: Approved
- **Deciders**: Core Architecture Team, OSPO Maintainer
- **Date**: 2026-09-01
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## Context

As NexusAI progresses toward Level 4 (Production Certified), the agent runtime requires seamless interoperability with the expanding ecosystem of Model Context Protocol (MCP) servers (such as local filesystem servers, database connectors, GitHub integrations, and developer environments).

Historically, adding new capabilities required authoring bespoke NexusAI plugins or tools inheriting from `BaseTool`. This approach presents limitations:
1. Tool development cannot leverage the broader open-source MCP community ecosystem.
2. Capability discovery for external tools is static rather than dynamic.
3. Managing separate external tool processes requires robust IPC, stdio streaming, and JSON-RPC 2.0 message dispatching.

---

## Decision

We introduce an asynchronous MCP Client and Tool Adapter subsystem under `nexusai.tools.mcp`:

1. **JSON-RPC 2.0 Stdio Client (`McpClient`)**:
   - Spawns and manages external MCP server processes over `asyncio.subprocess` using standard input/output (`stdio`).
   - Implements MCP lifecycle handshake (`initialize` $\rightarrow$ `notifications/initialized`, and graceful termination).
   - Executes standard RPC methods: `tools/list` and `tools/call`.
   - Incorporates request correlation IDs, timeouts, and process-group signal cleanup to eliminate zombie processes.

2. **Dynamic Tool Adapter (`McpToolWrapper`)**:
   - Subclasses `BaseTool` to seamlessly adapt remote MCP tool schemas into NexusAI's domain.
   - Generates dynamic Pydantic input models from JSON Schema declarations to ensure rigorous validation before execution.
   - Integrates with `SecurityGuard` risk assessment policy by attaching customizable `RiskLevel` configurations.

3. **Multi-Server Lifecycle Manager (`McpServerManager`)**:
   - Coordinates declarative configurations from `config/mcp_servers.yaml`.
   - Discovers tools from all connected servers and registers them dynamically into `ToolRegistry`.
   - Publishes `CapabilityAdvertisement` records to `RuntimeCapabilityDiscovery`, enabling dynamic planner capability graph generation without modifying core planning logic.
   - Handles graceful disconnection and capability revocation (`revoke_capability`).

---

## Alternatives Considered

1. **Bespoke Plugin Interfaces**:
   - Continue requiring custom Python modules in `plugins/`.
   - *Rejected*: Incompatible with external non-Python tools, language-agnostic servers, and community MCP distributions.
2. **gRPC-Only Sandboxing**:
   - NexusAI already implements gRPC sandboxing for untrusted local execution (`infrastructure/sandbox/`). However, external community servers standardize on MCP JSON-RPC, not NexusAI's internal protobuf schemas.
   - *Decision*: Keep internal gRPC sandbox for system commands while utilizing MCP for open ecosystem interoperability.

---

## Consequences

### Positive
- Plug-and-play compatibility with any standard MCP tool provider.
- Full compliance with unidirectional DAG import architecture (`nexusai.tools.mcp` $\rightarrow$ `nexusai.tools.base` & `nexusai.brain.ports`).
- Tools dynamically discovered and advertised to `RuntimeCapabilityDiscovery` without code modifications.
- Strict security guardrail evaluation before executing any MCP tool call.

### Negative
- Inter-process communication over stdio introduces minor I/O latency ($\approx 1\text{ms} - 5\text{ms}$) per tool invocation compared to in-process function execution.
- External server failure modes (e.g. process crash, malformed JSON) must be handled resiliently with explicit timeouts and error classifications.

---

## Validation Criteria

1. **Handshake & Protocol Fidelity**: Unit tests verify complete JSON-RPC 2.0 handshake and `tools/list` response parsing.
2. **Dynamic Schema Validation**: Arguments matching MCP input schemas execute cleanly; invalid inputs raise `ToolExecutionError`.
3. **Capability Lifecycle**: Registered tools appear in `ToolRegistry` and `RuntimeCapabilityDiscovery`; disconnected tools are cleanly revoked.
4. **Architecture Boundaries**: Zero illegal imports into `nexusai.brain` or circular package dependencies.
