# ADR-0015: Built-in Model Context Protocol (MCP) Server Pack

- **Status**: Approved
- **Date**: 2026-09-01
- **Author**: Core AI Team (`irsalshydiq <ichalprov@gmail.com>`)
- **Review Phase**: Phase 7 / Level 4 Milestone

---

## 1. Context

Previously in ADR-0013, NexusAI integrated the **Model Context Protocol (MCP)** with an asynchronous client (`McpClient`), multi-server manager (`McpServerManager`), CLI runner (`nexusai mcp`), and Web OS dashboard panel. However, the MCP servers referenced in the sample configuration (`config/mcp_servers.yaml`) still relied on external runtimes such as Node.js (`npx @modelcontextprotocol/server-filesystem`) or isolated Python packages via `uvx` (`uvx mcp-server-sqlite`).

Reliance on external runtimes introduced several operational bottlenecks:
1. **Failure in Offline / Air-Gapped Environments**: Running `npx` or `uvx` requires an active internet connection to download external packages at runtime.
2. **External Dependency Constraints (Node.js)**: Users operating in pure Python environments could not leverage standard MCP filesystem capabilities without installing Node/NPM.
3. **Absence of Out-of-the-Box Servers**: There were no core tool servers (Filesystem, SQLite, Web Fetcher) ready to run instantly from the NexusAI repository without external bootstrapping.

---

## 2. Decision

We decided to implement a native **Built-in MCP Server Pack** for NexusAI built on pure Python 3.12+ within the `nexusai.tools.mcp.servers` namespace:

1. **`McpServerBase` Framework (`nexusai.tools.mcp.servers.base`)**:
   - Base abstraction for Model Context Protocol servers communicating over standard I/O (stdio JSON-RPC 2.0).
   - Handles the official MCP protocol lifecycle (`2024-11-05`):
     - `initialize`: Protocol negotiation and server capabilities declaration.
     - `notifications/initialized`: Client readiness confirmation.
     - `ping`: Stdio latency health check.
     - `tools/list`: Export tool schema definitions (`McpToolDefinition`).
     - `tools/call`: Execute local handlers and return `McpCallToolResult`.
   - Guarantees that all JSON-RPC output streams purely to `sys.stdout` with immediate flushing, while diagnostic logs redirect to `sys.stderr`.

2. **Three Specialized Built-in MCP Servers**:
   - **Filesystem Server (`nexusai.tools.mcp.servers.filesystem`)**:
     - Provides tools: `read_file`, `write_file`, `list_directory`, `get_file_info`, `search_files`.
     - **Jail Sandboxing**: Validates every target path against the configured root directory to prevent directory traversal exploits (`../`).
   - **SQLite Server (`nexusai.tools.mcp.servers.sqlite`)**:
     - Provides tools: `read_query`, `write_query`, `list_tables`, `describe_table`.
     - Non-blocking asynchronous execution using `aiosqlite` with parameterized query support.
   - **Web Fetcher Server (`nexusai.tools.mcp.servers.web_fetcher`)**:
     - Provides tools: `fetch_url` (clean text/markdown extraction from HTML without scripts/styles) and `http_request` (generic GET/POST/PUT/DELETE).
     - Uses `httpx.AsyncClient` with configurable timeouts and response size limits.

3. **Default Configuration (`config/mcp_servers.yaml`)**:
   - Enables all three built-in servers by default using the standard Python module runner: `python3 -m nexusai.tools.mcp.servers.<module>`.

---

## 3. Alternatives Considered

1. **Retaining External Dependencies (npm / npx / uvx)**:
   - *Rejected*: Incurs high cold-start latency, risks failure in minimalist containers lacking Node.js, and exposes environments to external package supply chain attacks.
2. **Running Servers as In-Memory Threads (Instead of Stdio Subprocesses)**:
   - *Rejected*: Violates process isolation principles and official MCP specifications requiring strict process boundaries via stdio or SSE.

---

## 4. Consequences

### Positive Consequences
- **Zero-Dependency Setup**: Runs directly using existing NexusAI Python dependencies (`aiosqlite`, `httpx`).
- **Guaranteed Sandboxing**: The filesystem server enforces strict root directory jail boundaries.
- **Full Compatibility**: Servers strictly follow the official JSON-RPC 2.0 MCP specification, allowing integration not only with NexusAI, but also with external MCP ecosystems (Claude Desktop, Cursor, etc.).
- **Clean Observability**: Diagnostic logs remain isolated to `sys.stderr`, ensuring JSON-RPC stdio streams remain clean and uncorrupted.

### Negative Consequences
- Additional Python subprocesses incur a slight memory footprint (~30-40 MB RSS per active server process).

---

## 5. Validation Criteria

1. **Handshake & Protocol Verification**:
   - All `initialize`, `ping`, `tools/list`, and `tools/call` requests verified via unit tests in `tests/unit/test_mcp_builtin_servers.py`.
2. **Security & Sandboxing Test**:
   - Path traversal attempts (`../../etc/shadow`) on `FilesystemMcpServer` must be rejected with safe error responses.
3. **End-to-End Stdio Subprocess Test**:
   - `McpClient` successfully spawns `python3 -m nexusai.tools.mcp.servers.sqlite`, executes DDL & DML, and terminates cleanly without zombie processes.
4. **Static Analysis & Type Compliance**:
   - 100% pass on `ruff check` and `mypy --strict`.

---

## 6. Review Phase

- Milestone: Phase 7 / Level 4 Production Hardening
- Target Release: v1.0.0-rc1 / v1.0.0
