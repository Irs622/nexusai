---
status: accepted
audience:
  - ai-agents
  - contributors
  - security-team
owner:
  - security-team
applies_to:
  - src/nexusai/security
  - src/nexusai/tools
review_cycle: quarterly
last_reviewed: 2026-09-11
---

# ADR 0028: Capability-Based Tool Authorization and Execution Containment

## Status
Accepted

## Context
Following the implementation of Role-Based Access Control (RBAC) in ADR 0027, system roles (`viewer`, `operator`, `admin`, `system`) established *who* can access broad risk tiers. However, roles are coarse-grained:
1. An `admin` role possessed unrestricted access to execute any command via `TerminalTool`, creating a large attack surface where prompt injection or malicious planning could invoke destructive commands (e.g., `rm -rf /`).
2. The legacy `SecurityGuard` relied on a command blacklist (`forbidden_commands` in `config/security.yaml`), which is inherently fragile against shell aliasing, path encoding, pipes, and subshell invocation.
3. Security audits identified four critical implementation gaps:
   - **Workspace File System Tools (`ReadFileTool`, `ListDirectoryTool`)**: Paths were resolved without containment against a workspace root, allowing arbitrary path traversal (`../../etc/passwd`) and symlink escapes.
   - **MCP Web Fetcher Server (`WebFetcherMcpServer`)**: Performed arbitrary HTTP requests without private IP, loopback, or cloud metadata (169.254.169.254) filtering, and followed redirects blindly without hop-by-hop validation (SSRF vulnerability).
   - **Plugin Loader (`PluginLoader`)**: Dynamically imported plugin modules via `importlib.import_module()` before validating manifest capabilities, allowing untrusted code execution at import time.
   - **MCP Tool Dynamic Schemas (`McpToolWrapper`)**: Mapped unknown JSON Schema types to `Any` and used `extra="allow"`, allowing unexpected and unvalidated parameters into remote tool execution.

## Decision
We implement a comprehensive, fine-grained capability-based authorization engine and remediate all audit-identified tool execution vulnerabilities:

1. **Positive Capability Model (`Capability`, `CapabilityProfile`, `CapabilityResolver`)**:
   - Every tool action is authorized against positive capability grants: `(domain, action, resource, constraints)`.
   - Domains: `filesystem`, `shell`, `network`, `mcp`, `memory`, `applescript`, `tool`.
   - Resources support exact matching and glob/path recursion (`/workspace/**`, `git`, `pytest`, `*.pypi.org`, `*`).
   - Constraints validate execution bounds (`max_duration_seconds`, `max_file_size`, `allowed_extensions`, `allowed_commands`, `allowed_ports`).
   - Standard profiles configured in `config/capabilities.yaml`: `unrestricted_admin`, `coding_agent`, `readonly_agent`, and `default`.

2. **Default-Deny Policy in `SecurityGuard`**:
   - Replaces blacklist-based command filtering with positive capability verification: actions are denied by default unless explicitly covered by a granted capability.
   - Denied actions emit `ACTION_DENIED_CAPABILITY` audit events with full context (identity, domain, action, resource, denial reason) and raise `SecurityError`.
   - Allowed actions record the authorizing capability into the execution context.

3. **Workspace-Root Containment on File System Tools (`ReadFileTool`, `ListDirectoryTool`)**:
   - All paths are resolved and verified against `workspace_root` using `resolved.relative_to(workspace_root)`.
   - Directory traversal escapes and symlinks pointing outside the workspace root raise `PermissionError` and are blocked.

4. **SSRF Filtering & Hop-by-Hop Redirect Validation (`WebFetcherMcpServer`)**:
   - Outbound HTTP requests validate target schemes and pre-resolve DNS hostnames.
   - Block loopback (`127.0.0.0/8`, `::1`), RFC1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), and cloud metadata services (`169.254.169.254`).
   - Manual redirect handling with validation on every hop prevents redirect-based SSRF.

5. **Pre-Import Plugin Policy Enforcement (`PluginLoader`)**:
   - Plugin manifest capabilities are verified against `PluginPolicyEngine` *before* calling `importlib.import_module()`.
   - Untrusted modules without an approved manifest or trust listing are rejected prior to execution.

6. **Strict MCP Tool Schema Validation (`McpToolWrapper`)**:
   - Unsupported or unknown JSON Schema types raise `ToolExecutionError` rather than widening to `Any`.
   - Dynamically generated Pydantic input models enforce `ConfigDict(extra="forbid")`.
   - Tools without explicit parameters emit warning logs and enforce `extra="forbid"`.

## Alternatives Considered
- **Strictly Relying on Command Blacklists**: Rejected because blacklists cannot enumerate all dangerous shell constructs, scripts, and interpreter flags.
- **OCI Container Sandboxing Only**: Container sandboxing provides isolation at the kernel level, but does not provide application-level identity-aware authorization (e.g., differentiating read-only vs. read-write agents in the same workspace).

## Consequences

### Positive
- **Principle of Least Privilege**: Agents and users can be constrained to precise tools, directories, commands, and network domains.
- **Defense in Depth**: Combines RBAC (role tier), Capability (fine-grained grant), Input Sanitizer (safety check), and Approval Tokens (human-in-the-loop gate).
- **Audit Traceability**: Every permitted execution identifies the exact capability grant that authorized it.
- **Robust Against Path Traversal & SSRF**: Filesystem and network tools cannot escape workspace boundaries or access internal network services.

### Negative
- Configuration profiles must be maintained for new agent personas or workflows requiring additional commands.

## Validation Criteria
- Unit test suite `tests/unit/security/test_capability.py` covering model immutability, pattern matching, constraints, and YAML profile loading.
- Integration test suite `tests/integration/test_capability_enforcement.py` validating default-deny, shell command restrictions, duration limits, workspace containment, SSRF prevention, pre-import plugin checks, and MCP schema strictness.
- 100% test pass rate across the entire repository test suite.
- 0 violations in static analysis (`ruff`, `mypy --strict`) and 100/100 architecture score.

## Review Phase
Phase 3.2+ Hardening Review
