# ADR 0026: Security Hardening — Server-Side Approval Tokens, CORS Hardening, and Autonomous Bypass Remediation

## Status
Accepted

## Context
NexusAI exposes an HTTP REST API gateway and an autonomous LLM reasoning runtime (`BrainCoordinator`) designed to execute governed tools, including high-risk system commands (`execute_terminal`) and modifying file actions.

An architectural security audit identified several critical vulnerabilities:
1. **Approval Gate Client-Side Bypass (RCE Surface)**: The `POST /api/tools/execute` endpoint accepted a client-supplied boolean `user_confirmed: bool = False`. Any external HTTP caller could supply `user_confirmed: true` to bypass the human-in-the-loop authorization barrier and execute arbitrary commands via `TerminalTool` (`asyncio.create_subprocess_shell`).
2. **Permissive CORS Defaults**: `FastAPI` CORS was configured with `allow_origins=["*"]` and `allow_credentials=True`. This permitted malicious cross-origin websites in a user's browser to send requests to local or cluster instances of NexusAI.
3. **Autonomous Approval Bypass in Coordinator**: `BrainCoordinator.process_user_input()` defaulted `user_confirmed: bool = True` and hardcoded `ExecuteToolCommand(..., user_confirmed=True)` when dispatching LLM-generated tool calls. Furthermore, an ungoverned fallback (`tool_inst.execute()`) allowed tools to run without passing through the CQRS command bus.
4. **Permissive Security Defaults**: Shipped defaults in `config/security.yaml` included `strict_mode: false`, `auto_approve_low_risk: true`, and lacked critical user directories (`~/.ssh`, `~/.aws`, `~/.config`) in `protected_paths`.

## Decision

We introduce a defense-in-depth, cryptographic approval token architecture and harden API defaults:

### 1. Server-Side Approval Token Subsystem (`ApprovalTokenService`)
- We introduce `nexusai.security.approval_token.ApprovalTokenService`.
- For `HIGH` and `CRITICAL` risk tools, authorization requires a single-use server-issued approval token:
  $$\text{Payload} = \text{user\_id} \parallel \text{tool\_name} \parallel \text{SHA256}(\text{args}) \parallel \text{execution\_id} \parallel \text{expires\_at} \parallel \text{nonce}$$
  $$\text{Token} = \text{nexus\_appr\_} \parallel \text{nonce} \parallel \text{.} \parallel \text{expires\_at} \parallel \text{.} \parallel \text{HMAC-SHA256}(\text{secret}, \text{Payload})$$
- **Single-Use Replay Protection**: Nonces are atomically tracked and consumed. Reused tokens immediately yield `403 Forbidden`.
- **Short Validity Window**: Default TTL of 300 seconds (5 minutes). Expired tokens are rejected.
- **Strict Parameter Binding**: Changing any tool argument, tool name, or context invalidates the signature.

### 2. API Contract & Gateway Hardening
- The `user_confirmed` boolean field is removed from `ToolExecRequest` and `ChatRequest`.
- Dedicated endpoint `POST /api/v1/approvals/request` issues approval tokens.
- `POST /api/tools/execute` requires the `X-Approval-Token` header for `HIGH` and `CRITICAL` risk tools. Missing, expired, or invalid tokens return `403 Forbidden`.
- CORS is restricted: Wildcards (`*`) are disallowed. Default origin is `http://localhost:8000`, configurable via `NEXUSAI_ALLOWED_ORIGINS` and `config/default.yaml` (`api.allowed_origins`). `allow_credentials` defaults to `False`.

### 3. Policy Orchestrator Pattern in `SecurityGuard`
`SecurityGuard` is refactored into a pure policy orchestrator executing an ordered admission pipeline:
$$\text{Request} \longrightarrow \text{Identity/Auth} \longrightarrow \text{RBAC} \longrightarrow \text{Capability} \longrightarrow \text{Sanitizer} \longrightarrow \text{Approval Token Check} \longrightarrow \text{Execution}$$
Token validation logic is delegated entirely to `ApprovalTokenService`, maintaining single-responsibility separation.

### 4. BrainCoordinator Remediation
- Removed `user_confirmed=True` parameter default and hardcoded bypass.
- Removed direct `tool_inst.execute()` fallback: all execution must traverse the governed command bus.
- Model-generated tool calls undergo identical governance policies as external API requests.

### 5. Hardened Shipped Defaults
- `config/security.yaml`: `strict_mode: true`, `auto_approve_low_risk: false`.
- `protected_paths`: Expanded to block `~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/Library/Keychains`, and `/var/run/docker.sock`.

## Alternatives Considered
- **Symmetric Session Cookie Confirmation**: Required persistent browser session state and stateful HTTP sessions, incompatible with stateless CLI/API automation.
- **JWT (JSON Web Token) Approvals**: Heavier payload and dependencies (e.g. `pyjwt`). Compact HMAC-SHA256 tokens provide equivalent security guarantees with zero external dependencies.
- **Pre-execution Interactive Stdin Prompt**: Incompatible with automated API microservices and distributed DAG workers.

## Consequences

### Positive
- **Complete Elimination of RCE Surface**: HTTP clients and malicious prompts can no longer bypass human approval for sensitive tools.
- **CORS Protection**: Prevents cross-site request forgery and browser-driven local port exploitation.
- **Auditable & Tamper-Resistant**: Every approval token is cryptographically tied to the exact command and arguments.
- **Clean Component Decoupling**: Prepares the pipeline for upcoming RFCs and issues (#31 RBAC and #34 Capability-based authorization).

### Negative
- Clients executing `HIGH` risk tools via REST API must perform a two-step flow (`POST /api/v1/approvals/request` followed by `POST /api/tools/execute` with `X-Approval-Token`).

## Validation Criteria
- `tests/unit/security/test_approval_token.py`: 100% pass covering issuance, validation, replay rejection, expiration, and argument tampering.
- `tests/unit/test_api.py`: Verified 403 response on missing/replayed token, 200 on valid token, and hardened CORS headers.
- `tests/unit/test_brain.py`: Verified `BrainCoordinator` halts critical actions when approval is missing and succeeds when valid token is supplied.
- All unit, integration, and architecture tests pass without regression.

## Review Phase
Quarterly Architectural Governance Review & Security Audit Cycle 2026-Q3.
