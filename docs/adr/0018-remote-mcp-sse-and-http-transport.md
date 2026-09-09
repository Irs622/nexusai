# 18. Remote Model Context Protocol (MCP) Server-Sent Events (SSE) & HTTP Streaming Transport

- **Status**: Approved
- **Deciders**: Core Architecture Team, OSPO Maintainer
- **Date**: 2026-09-09
- **Review Phase**: Phase 7 / Level 4 Milestone (Issue #18)

---

## Context

Following the adoption of ADR 0013 (*Model Context Protocol Client & Tool Adapter Integration*) and ADR 0015 (*Built-in Native MCP Server Pack*), NexusAI supported MCP execution exclusively over standard I/O (`stdio` JSON-RPC 2.0 subprocesses).

While `stdio` is optimal for co-located local subprocesses, modern enterprise deployments require NexusAI agents to interact with distributed microservices, Kubernetes pods, remote SaaS MCP gateways, and containerized tool clusters. To support distributed agent topologies, the Model Context Protocol specification (2024-11-05) standardizes remote server communication using:
1. HTTP Server-Sent Events (`text/event-stream`) for continuous asynchronous server-to-client message streaming.
2. HTTP POST requests for client-to-server JSON-RPC 2.0 message dispatches.
3. Dynamic session-aware message endpoint negotiation via `event: endpoint`.

---

## Decision

We introduce a first-class remote MCP transport subsystem under `nexusai.tools.mcp`:

1. **Polymorphic Client Interface (`BaseMcpClient`)**:
   - Establish an abstract base class `BaseMcpClient` in `nexusai.tools.mcp.base` defining standardized lifecycle (`start`, `stop`, `ping`) and discovery contracts (`list_tools`, `call_tool`, `list_prompts`, `list_resources`).
   - Refactor the existing `McpClient` (`stdio`) to inherit from `BaseMcpClient`, guaranteeing 100% backward compatibility with all existing tool wrappers and callers.

2. **Asynchronous HTTP & SSE Connection Transport (`McpHttpTransport`)**:
   - Built on `httpx.AsyncClient` with connection pooling (`httpx.Limits(max_connections=50, max_keepalive_connections=20)`).
   - Complies with the W3C EventSource standard, parsing line-delimited SSE frames (`event`, `data`, `id`, `retry`) and ignoring keepalive comment lines (`:`).
   - Non-blocking streaming generator allowing cooperative multitasking across concurrent agent loops.

3. **Remote SSE Client (`McpSseClient`)**:
   - Discovers message dispatch endpoints dynamically from initial `event: endpoint` announcements or base URL defaults.
   - Coordinates protocol initialization handshake (`initialize` $\rightarrow$ `notifications/initialized`).
   - Correlates JSON-RPC responses by request ID across both asynchronous SSE streams and direct HTTP POST responses.
   - Implements resilient automatic reconnection with exponential backoff (`reconnect_backoff_seconds * 2^attempt`) and periodic background heartbeat pings.

4. **Multi-Transport Declarative Server Management (`McpServerManager`)**:
   - Dynamically parses `transport: stdio | sse | http` from `config/mcp_servers.yaml`.
   - Instantiates `McpSseClient` for remote streaming endpoints and `McpClient` for local processes seamlessly.

---

## Alternatives Considered

1. **WebSockets Transport**:
   - *Considered*: WebSockets provides full-duplex communication over a single TCP socket.
   - *Rejected*: The official MCP 2024-11-05 specification mandates SSE over HTTP for remote transport rather than WebSockets, maximizing compatibility with corporate firewalls, HTTP/2 multiplexing, and standard load balancers.
2. **Third-Party External MCP Client Libraries**:
   - *Considered*: Relying on external Python MCP SDKs.
   - *Rejected*: External SDKs introduce heavy dependency chains and potential C-extension conflicts. Implementing clean, dependency-isolated transport using NexusAI's existing `httpx` engine preserves our strict architecture DAG and zero-technical-debt guarantees.

---

## Consequences

### Positive
- Seamless connectivity to remote MCP servers across Kubernetes, microVMs, and cloud environments.
- 100% backward compatibility for all existing stdio servers and `McpToolWrapper` consumers.
- Native resilience via exponential backoff reconnects and proactive heartbeat monitoring.
- Preserves top-down unidirectional architecture DAG score at 100/100.

### Negative
- Requires maintaining an active HTTP/SSE connection pool in memory for long-running remote servers.
- Network latency inherent to remote HTTP transport compared to direct local IPC pipes.

---

## Validation Criteria

1. **Protocol Handshake & Discovery**: Client discovers tools, prompts, and resources from mock remote SSE servers.
2. **Execution Flow**: `tools/call` dispatches request and validates output through both SSE events and direct HTTP responses without blocking event loop.
3. **Resilience**: Connection drops trigger auto-reconnection with exponential backoff up to configured limit.
4. **Quality Gates**: All unit tests pass, `mypy --strict` passes with 0 errors, and architectural compliance remains at 100.0%.
