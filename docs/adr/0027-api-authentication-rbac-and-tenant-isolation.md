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
  - src/nexusai/api
review_cycle: quarterly
last_reviewed: 2026-09-11
---

# ADR 0027: API Authentication, Role-Based Access Control (RBAC), and Multi-Tenant Isolation

## Status
Accepted

## Context
NexusAI operates as a production runtime providing REST, SSE, and interactive dashboard interfaces. Prior to this decision:
1. All HTTP endpoints lacked authentication and authorization gates. Any network client could issue requests, including `POST /api/tools/execute`, which can execute commands via `TerminalTool`.
2. There was no concept of caller identity or tenant context (`identity -> authentication -> authorization -> tenant scope -> capability -> execution`).
3. Application state (`app.state.*`: audit chains, governance budgets, pending approvals, studio DAG plans) was application-global, creating high security risk of cross-tenant contamination, data leakage, and unauthorized resource consumption.
4. Autonomous LLM execution paths did not propagate caller identity down to the CQRS command bus or audit event generation.

## Decision
We implement a multi-layered security architecture consisting of:
1. **API Key Authentication Layer (`ApiKeyService` & `AuthMiddleware`)**:
   - HTTP requests are authenticated via the `X-NexusAI-API-Key` header.
   - Zero-plaintext storage: only canonical SHA-256 hashes (`key_hash`) are persisted or kept in memory.
   - Keys bind an explicit `tenant_id`, `user_id`, and `role`.
   - Key lifecycle supports immediate revocation and expiration.
   - Sliding-window rate limiter per API key (default 100 req/min).
   - Exempt paths are strictly limited to non-sensitive health probes (`/health/live`, `/health/ready`, `/healthz`, `/readyz`), OpenAPI schema documentation (`/docs`, `/openapi.json`, `/redoc`), and static UI assets (`/`, `/studio`, `/static/*`).
   - Unauthenticated or unauthorized access to protected endpoints yields `401 Unauthorized`.
   - Rate limit exceeded yields `429 Too Many Requests`.

2. **Role-Based Access Control Engine (`RbacEngine` & `Role`)**:
   - Four hierarchical roles: `viewer` (10) < `operator` (20) < `admin` (30) < `system` (40).
   - `viewer`: Read-only access (`GET /api/status`, `/api/tools`, `/api/v1/dag/plans`, `/api/v1/governance/budget`, `/api/v1/audit/events`). Blocked from tool execution or state mutation (`403 Forbidden`).
   - `operator`: Permitted to execute `LOW` and `MEDIUM` risk tools. Blocked from `HIGH` and `CRITICAL` risk tools (`403 Forbidden`).
   - `admin` & `system`: Permitted tool execution across all risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), subject to approval tokens for high/critical risks.
   - Anti-Escalation Invariant: Callers cannot assign roles without admin/system authority, cannot assign roles exceeding their own hierarchy level, and cannot self-escalate.

3. **Tenant State Isolation (`TenantContext` & Partitioned State)**:
   - Ambient tenant and identity propagation via `TenantContext` backed by thread-safe, coroutine-safe `contextvars.ContextVar`.
   - Partitioning of stateful runtime structures:
     - `app.state.tenant_audit_chains[tenant_id]`
     - `app.state.tenant_governance_budgets[tenant_id]`
     - `app.state.tenant_pending_approvals[tenant_id]`
     - `app.state.tenant_studio_plans[tenant_id]`
   - Absolute isolation: Tenant A cannot inspect, tamper with, approve, or exhaust Tenant B's state, audit logs, or quota.

4. **End-to-End Identity Propagation**:
   - `Request` -> `AuthMiddleware` -> `Identity` & `TenantContext` -> `ExecutionContext` -> `ExecuteToolCommand(user_id=...)` -> `SecurityGuard` / `RbacEngine` -> CQRS Command Bus -> `ToolExecutedEvent` -> `AuditEvent(actor=user_id)`.

## Alternatives Considered
1. **JWT (JSON Web Tokens)**:
   - *Considered*: Stateless signed JWT bearer tokens.
   - *Rejected for v1*: Increased key management complexity, revocation required distributed token blacklisting / Redis. API key hashing provides immediate revocation, audit traceability, and zero plaintext exposure with minimal operational overhead.
2. **Global Single-Tenant Middleware**:
   - *Considered*: Simple static bearer token matching an environment variable.
   - *Rejected*: Violates multi-tenant isolation requirements and prevents differentiating between read-only viewers, operators, and administrators.
3. **Database-backed OAuth2 / OIDC**:
   - *Deferred to v2*: Future enterprise integration can plug directly into `AuthMiddleware` by providing an alternate authenticator that populates `request.state.identity` and `TenantContext`.

## Consequences
### Positive
- Prevents unauthenticated remote code execution and API probing.
- Strict multi-tenant isolation guarantees zero data leakage across workspaces.
- Fine-grained RBAC prevents unauthorized tool execution and role escalation.
- Full cryptographic audit trails now record the verified `actor` of every operation.
- Backward compatibility preserved for testing via pre-registered test admin credentials.

### Negative
- All HTTP API clients must now provide a valid `X-NexusAI-API-Key` header.
- In-memory rate limiting requires distributed state sync if horizontally scaled without sticky sessions (handled in distributed roadmap).

## Validation Criteria
- Automated unit test suite covering key generation, hashing, verification, revocation, and expiration (`tests/unit/security/test_authentication.py`).
- Automated unit test suite covering RBAC risk matrix, HTTP methods, anti-escalation, and SecurityGuard integration (`tests/unit/security/test_authorization.py`).
- Automated integration test suite demonstrating full multi-tenant isolation of audit chains, approvals, budgets, and RBAC boundaries (`tests/integration/test_tenant_isolation.py`).
- Architecture fitness functions maintain 100/100 score and 0 debt.
- All pre-existing test suites pass without regression.

## Review Phase
- Phase 3.2 Security and Identity Governance.
