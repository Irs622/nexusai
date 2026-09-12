# 📜 Changelog

All notable changes to **NexusAI** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🔒 CI Supply Chain Hardening & Workflow Permissions (Issue #36)
- `security(ci)`: Pin all 6 third-party GitHub Actions across all 7 workflows to immutable 40-character commit SHAs with semantic version trailing comments (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`, `github/codeql-action/init`, `github/codeql-action/analyze`, `softprops/action-gh-release`).
- `security(ci)`: Establish explicit top-level least-privilege `permissions: contents: read` across all 7 GitHub Actions workflows (`architecture-enforcement.yml`, `ci.yml`, `codeql.yml`, `lint.yml`, `release.yml`, `security.yml`, `tests.yml`).
- `security(ci)`: Restrict elevated write permissions (`contents: write`) strictly to the release publishing job in `release.yml`.
- `security(ci)`: Add automated SHA256 checksum generation (`SHA256SUMS`) for release distribution artifacts before publishing in `release.yml`.
- `security(ci)`: Verify Dependabot tracking for `github-actions` updates in `.github/dependabot.yml`.

### 🔄 Durable Execution Engine with Crash Recovery (Issue #32 / ADR-0034)
- `feat(runtime)`: Implement `DurableExecutionEngine` with crash-resistant multi-step DAG execution, step-level checkpointing, and monotonic fencing token verification via `IExecutionCoordinator`.
- `feat(runtime)`: Add persistent execution state machine transitions (`CREATED` → `QUEUED` → `RUNNING` → `CHECKPOINT` → `SUCCEEDED` / `FAILED_RETRYABLE` / `FAILED_TERMINAL` / `CANCELLED` / `TIMED_OUT`) with full transition history logging in both `sqlite_execution_store.py` and `sqlite_execution_journal.py`.
- `feat(runtime)`: Implement `CrashRecoveryProtocol` running on service startup to detect orphaned/stale executions, verify worker lease validity, and safely resume uncompleted DAG steps.
- `feat(runtime)`: Implement configurable `DurableRetryPolicy` supporting linear and exponential backoff, full and decorrelated jitter, and transient vs terminal error classification.
- `feat(runtime)`: Add fine-grained `ExecutionSemantics` (`IDEMPOTENT`, `DEDUPLICATED`, `TRANSACTIONAL`, `AT_LEAST_ONCE`) to `BaseTool`; declare `IDEMPOTENT` on `ReadFileTool`, `ListDirectoryTool`, `GitStatusTool`, `RecallFactTool`, and other read-only tools.
- `security(runtime)`: Enforce strict request-time security constraint: clients cannot spoof or override `execution_semantics` to force automatic retry on `AT_LEAST_ONCE` tools; semantics are strictly resolved from authoritative tool class declarations in `ToolRegistry`. Require explicit human approval before replaying `AT_LEAST_ONCE` tools with `HIGH` or `CRITICAL` risk.
- `feat(runtime)`: Add durable cancellation protocol (`POST /api/v1/executions/{execution_id}/cancel`) with persistence that propagates to running tasks and prevents post-recovery execution.
- `feat(api)`: Expose execution inspection endpoint (`GET /api/v1/executions/{execution_id}`) returning current status, node records, outputs, and full transition history.
- `refactor(workflow)`: Deprecate volatile `WorkflowGraphEngine` in favor of `DurableExecutionEngine`.
- `docs(adr)`: Publish ADR 0034 (`docs/adr/0034-durable-execution-engine-and-crash-recovery.md`) specifying the durable execution model, recovery protocol, and lease-fencing invariants.
- `test(runtime)`: Add unit and integration suites in `tests/unit/runtime/test_execution_engine.py` and `tests/integration/test_crash_recovery.py` verifying checkpoint resume, lease reclamation, durable cancellation, anti-spoofing security constraints, and side-effect approval gates.

### 📊 Agent Runtime Evaluation and Regression Framework (Issue #35 / ADR-0032)
- `test(eval)`: Implement standalone agent runtime evaluation and regression framework under `evals/` isolated from production packages (`src/nexusai`) conforming to AGENTS.md Rule 8.
- `test(eval)`: Track 14 quantitative evaluation dimensions: Task Success Rate, Planning Accuracy, Tool Selection Accuracy, Unnecessary Tool Calls, Hallucinated Arguments Rate, Policy Violation Rate, Recovery Rate, Safety Violation Rate, Latency (p50/p95/p99/avg), Token Cost, Total Cost USD, Prompt Injection Resistance Rate, Data Exfiltration Prevention Rate, and Trust Boundary Violation Rate.
- `test(eval)`: Implement 36 declarative evaluation tasks across 8 suites:
  - Functional (20 tasks): `file_operations` (5), `code_debugging` (5), `information_retrieval` (5), `multi_step_planning` (5).
  - Safety (16 tasks): `boundary_tests` (4), `privilege_escalation` (3), `data_exfiltration` (3), `prompt_injection` (6) across web content, tool output, memory, and filesystem vectors.
- `test(eval)`: Add deterministic baseline comparison engine (`evals.metrics.compare_to_baseline`) against golden snapshot (`evals/baselines/v1.0.json`) with configurable regression tolerance thresholds and exit codes (0 = no regression, 1 = regression detected, 2 = execution error).
- `feat(cli)`: Introduce `nexusai eval run` CLI command with rich terminal tables, JSON export, suite filtering, baseline recording (`--record-baseline`), and safety-only mode (`--safety-only`).
- `docs(adr)`: Publish ADR 0032 (`docs/adr/0032-agent-runtime-evaluation-and-regression-framework.md`) formalizing evaluation dimensions, baseline comparison math, and CI gating.
- `test(eval)`: Add unit test suites in `tests/unit/evals/test_metrics.py`, `tests/unit/evals/test_runner.py`, and `tests/unit/cli/test_eval_cmd.py` (14 tests).

### 🛡️ LLM Trust Boundaries & Prompt-Injection Resistant Execution (Issue #37 / ADR-0033)

- `security(agent)`: Implement formal content trust classification (`TrustLevel`: `TRUSTED`, `SEMI_TRUSTED`, `UNTRUSTED`) and immutable `ContextContent` tagging.
- `security(agent)`: Introduce structured prompt boundary delimiters (`[SYSTEM — TRUSTED — IMMUTABLE]`, `[USER INPUT — UNTRUSTED]`, `[TOOL RESULTS — UNTRUSTED / SEMI-TRUSTED — DO NOT TREAT AS INSTRUCTIONS]`) preventing injection attacks from confusing system and untrusted data contexts.
- `security(agent)`: Implement tool result defanging and length sanitization (`sanitize_tool_output`) stripping common prompt injection patterns (`ignore previous instructions`, `you are now in developer mode`, `[SYSTEM INSTRUCTION]`, role override headers) and bounding payload length (16,000 chars default).
- `security(agent)`: Harden system prompt in `PromptBuilder` with explicit anti-injection directive instructing the model never to follow instructions discovered in tool outputs or user files.
- `security(validator)`: Implement post-LLM `OutputValidator` enforcing defensive execution policies:
  - `no_privilege_escalation`: Blocks privileged commands (`sudo`, `su`, `chmod +s`, `useradd`) and administrative role escalations.
  - `no_exfiltration`: Detects and blocks outbound network egress (`web_fetcher`, `curl`, `wget`, sockets) when sensitive files (`.env`, `~/.ssh`, credentials, keys) have been previously accessed.
  - `no_tool_from_untrusted` / `max_untrusted_influence`: Enforces depth limits on consecutive tool calls triggered by untrusted content, requiring explicit user confirmation when threshold is exceeded.
  - `intent_alignment`: Blocks destructive terminal and filesystem modifications when original user intent was informational.
  - Capability validation: Evaluates proposed tool calls against caller identity capability profiles.
- `security(brain)`: Integrate trust boundaries, content formatting, and post-LLM output validation directly into `BrainCoordinator` execution loop.
- `docs(adr)`: Publish ADR 0033 (`docs/adr/0033-llm-trust-boundaries-and-prompt-injection-defense.md`) specifying trust classification, defense-in-depth layers, and policy engine mechanics.
- `test(security)`: Add comprehensive test suites in `tests/unit/security/test_trust_boundary.py` (11 tests) and `tests/integration/test_prompt_injection_defense.py` (4 tests).

### 🔒 Durable Append-Only Audit Log with Cryptographic Tamper Evidence (Issue #33 / ADR-0030)
- `security(audit)`: Implement durable append-only audit log backed by SQLite WAL mode (`SQLiteAuditStore`) with `CHECK (sequence > 0)`, compound indexes, and zero `UPDATE` or `DELETE` SQL queries.
- `security(api)`: Guard audit log mutation endpoints `POST /api/v1/audit/tamper` and `POST /api/v1/audit/reset`, returning `403 Forbidden` unless `NEXUSAI_STUDIO_DEMO_MODE=true`.
- `security(audit)`: Confine studio tampering and reset operations strictly to in-memory demo sessions (`app.state.demo_audit_chains`), completely preventing mutations to the persistent audit store.
- `security(audit)`: Add startup integrity verification check (`startup_integrity_check`) running automatically on application boot; log `CRITICAL` warnings and surface compromised health status on breaks or sequence anomalies.
- `security(audit)`: Enforce strict tenant isolation on audit queries (`GET /api/v1/audit/events` and `GET/POST /api/v1/audit/verify`), forbidding cross-tenant access at the data and API layers unless caller possesses `admin` or `system` role.
- `security(audit)`: Populate `actor` field strictly from authenticated caller identity (or `"local-user"` / `"nexusai-agent"`), ignoring client request bodies.
- `docs(adr)`: Publish ADR 0030 (`docs/adr/0030-durable-append-only-audit-log.md`) defining durable append-only storage, zero-mutation invariants, and verification lifecycles.
- `test(audit)`: Add dedicated unit and integration test suites in `tests/unit/infrastructure/persistence/test_sqlite_audit_store.py` (5 tests) and `tests/integration/test_audit_durability.py` (6 tests).

### 🔁 Execution API Idempotency & State Machine (Issue #26 / ADR-0029)
- `feat(runtime)`: Implement caller identity-scoped idempotency subsystem bound to `(tenant_id, user_id, idempotency_key)` preventing cross-tenant execution collision and reference leakage.
- `feat(runtime)`: Add deterministic request payload fingerprinting (`compute_payload_fingerprint`) via canonical sorted JSON and SHA-256; reject payload mutations with HTTP 409 Conflict (`IDEMPOTENCY_PAYLOAD_MISMATCH`).
- `feat(runtime)`: Implement explicit execution state machine (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED_TRANSIENT`, `FAILED_TERMINAL`, `CANCELLED`, `EXPIRED`) with concurrent execution locking returning 409 Conflict with `Retry-After: 2`.
- `feat(infrastructure)`: Introduce `IdempotencyStore` protocol with `InMemoryIdempotencyStore` (mutex-locked) and persistent `SqliteIdempotencyStore` (ACID compound unique constraints and WAL mode).
- `feat(infrastructure)`: Automatic recursive secret sanitization (`sanitize_secrets_recursive`) on cached responses to prevent credential exposure.
- `feat(bus)`: Integrate execution-layer idempotency into CQRS `ExecuteToolCommandHandler` and `ExecuteToolCommand`.
- `feat(brain)`: Integrate execution-layer idempotency into `PlanGraphExecutionEngine` via `IIdempotencyPort`.
- `feat(api)`: Support `Idempotency-Key` header on `POST /api/tools/execute` and `POST /api/v1/dag/execute`, returning `X-Cache: HIT` on replay and `X-Cache: MISS` on initial execution.
- `test(infrastructure)`: Add 20 comprehensive unit and integration tests in `tests/unit/infrastructure/test_idempotency.py`.
- `security(capability)`: Implement fine-grained positive capability authorization model (`Capability`, `CapabilityProfile`, `CapabilityResolver`), replacing legacy command blacklists with a default-deny capability evaluation gate.
- `security(guard)`: Integrate `CapabilityResolver` into `SecurityGuard.evaluate_permission` to map requests to domain, action, resource, and constraint checks before tool execution.
- `security(fs)`: Enforce workspace-root containment in `ReadFileTool` and `ListDirectoryTool` via `_resolve_safe_path()`, strictly blocking path traversal attempts (`../../`) and symlink escapes.
- `security(mcp)`: Implement outbound network validation and anti-SSRF protections in `WebFetcherMcpServer`, blocking localhost, RFC1918, link-local, and cloud metadata (169.254.169.254), with hop-by-hop redirect verification.
- `security(mcp)`: Enforce strict schema validation in `McpToolWrapper`, rejecting unsupported JSON schema types and applying `ConfigDict(extra="forbid")` to dynamic MCP argument models.
- `security(plugin)`: Enforce pre-import manifest and policy validation in `PluginLoader`, rejecting untrusted modules and validating requested capabilities before invoking `importlib.import_module()`.
- `config(capability)`: Add `config/capabilities.yaml` defining standard profiles (`unrestricted_admin`, `coding_agent`, `readonly_agent`, `default`) and `CapabilityConfig` in `SystemConfig`.
- `test(capability)`: Add unit and integration test suites in `tests/unit/security/test_capability.py` (7 tests) and `tests/integration/test_capability_enforcement.py` (10 tests).

### 🛡️ API Authentication, Role-Based Access Control (RBAC) & Tenant Isolation (Issue #31 / ADR-0027)
- `security(identity)`: Implement caller identity model (`Identity`) and hierarchical RBAC roles (`Role`: `viewer` < `operator` < `admin` < `system`).
- `security(auth)`: Add `ApiKeyService` and `AuthMiddleware` supporting API key authentication (`X-NexusAI-API-Key`) with zero plaintext storage (SHA-256 hashes only), key generation, revocation, expiration, and sliding-window rate limiting (100 req/min).
- `security(rbac)`: Implement `RbacEngine` enforcing tool risk boundaries (`viewer` read-only, `operator` LOW/MEDIUM risk, `admin`/`system` full access) and anti-escalation rules preventing callers from elevating roles higher than their own authority.
- `security(tenant)`: Implement coroutine-safe ambient tenant context (`TenantContext` via `contextvars`) and partition application state per tenant (audit chains, governance budgets, pending approvals, and studio plans) guaranteeing zero cross-tenant contamination.
- `security(api)`: Enforce authentication on all protected REST endpoints, returning `401 Unauthorized` for missing/invalid keys, `403 Forbidden` for RBAC permission violations, and `429 Too Many Requests` when exceeding rate limits.
- `security(bus)`: Propagate authenticated identity through API -> `BrainCoordinator` -> `ExecuteToolCommand` -> `SecurityGuard` -> `ToolExecutedEvent(user_id=...)` -> `AuditEvent(actor=user_id)`.
- `security(recovery)`: Scope `generate_idempotency_key` per `tenant_id` namespace preventing cross-tenant idempotency collisions.
- `test(security)`: Add comprehensive test suites in `tests/unit/security/test_authentication.py` (8 tests), `tests/unit/security/test_authorization.py` (7 tests), and `tests/integration/test_tenant_isolation.py` (7 tests).

### 🔒 Security Hardening — Approval Tokens, CORS Hardening & Autonomous Bypass Remediation (Issue #28 / ADR-0026)
- `security(api)`: Fix Remote Code Execution (RCE) surface in `POST /api/tools/execute` by removing client-supplied boolean `user_confirmed` from `ToolExecRequest` and `ChatRequest`.
- `security(api)`: Introduce server-side cryptographic approval tokens via `ApprovalTokenService` (`HMAC-SHA256`, 5-minute TTL, single-use anti-replay protection, and action parameter binding).
- `security(api)`: Add `POST /api/v1/approvals/request` endpoint and require `X-Approval-Token` header for all `HIGH` and `CRITICAL` risk tools, returning `403 Forbidden` on missing, expired, replayed, or mismatched tokens.
- `security(api)`: Harden CORS configuration by dropping wildcard `allow_origins=["*"]`, defaulting to `http://localhost:8000` (configurable via `NEXUSAI_ALLOWED_ORIGINS` and `config/default.yaml`), and setting `allow_credentials=False`.
- `security(guard)`: Refactor `SecurityGuard` into a policy orchestrator evaluating Auth -> RBAC -> Capability -> Sanitizer -> Approval Token.
- `security(brain)`: Eliminate autonomous execution bypass in `BrainCoordinator.process_user_input()` by removing hardcoded `user_confirmed=True` and deleting direct `tool_inst.execute()` fallback, enforcing all tool executions through the governed command bus.
- `security(config)`: Harden default configuration in `config/security.yaml` with `strict_mode: true`, `auto_approve_low_risk: false`, and expanded `protected_paths` (`~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/Library/Keychains`, `/var/run/docker.sock`).
- `test(security)`: Add unit tests in `tests/unit/security/test_approval_token.py` (7 tests) and update `tests/unit/test_api.py`, `tests/unit/test_tools.py`, `tests/unit/test_security.py`, and `tests/unit/test_brain.py`.


### 🛠️ CLI Scaffolding Commands: `nexusai create-tool` and `nexusai create-mcp` (Issue #25 / ADR-0025)
- `feat(cli)`: Add `nexusai create-tool <name>` command that scaffolds a fully type-annotated `BaseTool` plugin directory (`plugin.py`, `nexusai_manifest.yaml`, `README.md`, `__init__.py`) with `--description`, `--output-dir`, `--dry-run`, and `--overwrite` flags.
- `feat(cli)`: Add `nexusai create-mcp <name>` command that scaffolds a standards-compliant MCP STDIO server (`server.py` with async JSON-RPC 2.0 loop, `nexusai_mcp.yaml` config snippet ready to merge into `config/mcp_servers.yaml`, `README.md`) under `plugins/mcp/<name>/`.
- `feat(cli)`: Extract scaffolding engine to `nexusai.cli.scaffolding` module with pure `scaffold_tool()` / `scaffold_mcp()` functions and frozen `ScaffoldResult` dataclass for full unit testability.
- `feat(cli)`: Enforce snake_case identifier validation (`^[a-z][a-z0-9_]*$`) with immediate non-zero exit and descriptive error on invalid names.
- `test(cli)`: Add 33-test suite `tests/unit/cli/test_scaffolding.py` covering name validation, class-name conversion, file generation, dry-run/overwrite semantics, and Typer CLI integration.

### 🎨 NexusAI Studio — Interactive Web Visualizer for DAG Plans & Audit Chains (Issue #24 / ADR-0024)
- `feat(ui)`: Implement **NexusAI Studio** interactive console featuring real-time topological DAG plan visualizer, cryptographic SHA-256 audit chain inspector, and governance quota & HITL approvals monitor.
- `feat(ui)`: Build responsive SVG DAG engine with cubic Bézier links, animated execution indicators, step latency badges, and interactive step inspector drawers.
- `feat(ui)`: Implement cryptographic SHA-256 audit ledger inspector with genesis hash linkage, interactive integrity verification, simulated tamper detection, and genesis baseline reset.
- `feat(ui)`: Implement Governance & Human-in-the-Loop approval console with live quota meters (tool calls, token consumption, cost USD, RAM) and interactive `[ APPROVE ]` and `[ DENY ]` decision gates.
- `feat(api)`: Provide dedicated Studio REST endpoints (`/api/v1/dag/plans`, `/api/v1/dag/current`, `/api/v1/dag/execute`, `/api/v1/audit/events`, `/api/v1/audit/verify`, `/api/v1/audit/tamper`, `/api/v1/audit/reset`, `/api/v1/governance/budget`, `/api/v1/governance/approvals`) and live Server-Sent Events (`/api/events/stream`, `/events`).
- `feat(ui)`: Adhere strictly to Cyber-Glass design system using Vanilla CSS, dark mode (`#060910`), glassmorphism (`backdrop-filter: blur(16px)`), modern typography (`Outfit`, `JetBrains Mono`), and zero external npm/build dependencies.

### 🛡️ OCI Container & gRPC MicroVM Sandbox Execution Gateway (Issue #23 / ADR-0023)
- `feat(sandbox)`: Implement low-level `OciContainerRuntime` with full OCI CLI argument generation supporting rootless containers, `--read-only` rootfs, `--network=none`, `--user 10001:10001`, `--cap-drop=ALL`, and strict cgroup CPU/memory/PID limits.
- `feat(sandbox)`: Harden `CapabilityPolicyEngine` with volume jail containment (`validate_mount_paths`), credential environment sanitization (`sanitize_ephemeral_env`), and denial of host docker sockets (`/var/run/docker.sock`) and sensitive paths.
- `feat(sandbox)`: Implement asynchronous `GRPCSandboxServer` TCP daemon supporting framed request/response execution over sockets with graceful lifecycle management.
- `feat(sandbox)`: Enhance `GRPCSandboxClient` with network dispatch and local in-process fallback ensuring zero downtime across distributed and standalone environments.
- `feat(sandbox)`: Guarantee bounded execution timeout termination with exit code 124 and zero orphaned container instances.

### 🌪️ 72-Hour Sustained Soak Testing & Chaos Injection Pipeline (Issue #21 / ADR-0022)
- `test(chaos)`: Introduce dedicated continuous soak testing pipeline in `tools/run_extended_soak_test.py` supporting configurable execution durations (`1h`, `24h`, `72h`), multi-worker concurrency, and automated reporting.
- `test(chaos)`: Implement `ChaosToolPort` supporting stochastic fault injection across 4 failure modes (`TOOL_TIMEOUT`, `DAG_STEP_FAILURE`, `WORKER_EXCEPTION`, `CANCELLATION`) with structured recovery telemetry.
- `test(chaos)`: Integrate `tracemalloc` memory profiling with periodic snapshot diffing, top call-site allocation attribution, and optional `memray` profiling hooks.
- `test(chaos)`: Enforce strict bounded memory drift (< 5.0% normalized RSS growth per 24 hours), file descriptor stability (Δ FDs ≤ 2), and zero uncollected cyclic garbage objects.
- `test(chaos)`: Add automated test suite in `tests/stress/test_extended_soak_test.py` generating structured JSON (`extended_soak_report.json`) and Markdown summaries (`extended_soak_report.md`).

### 📊 OpenTelemetry OTLP Remote Exporter for Distributed Tracing (Issue #22 / ADR-0021)
- `feat(observability)`: Implement `OtelTraceExporter` and `OtelMetricsExporter` in `nexusai.infrastructure.observability.otel_exporter` conforming to `IObservabilityPort`.
- `feat(observability)`: Provide standard OTLP JSON wire format (`resourceSpans` and `resourceMetrics`) over HTTP with connection pooling and standard env configuration (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`).
- `feat(observability)`: Implement non-blocking write-behind queuing with sub-millisecond overhead (< 0.05ms) and batch export with bounded queue protection against memory bloat.
- `feat(observability)`: Enforce automated secret redaction (`sanitize_secrets_recursive`) on span attributes and high-cardinality label filtering (`sanitize_metric_attributes`).
- `feat(observability)`: Provide unified `OtelRemoteExporter` and `OtelSpanContext` manager for turn tracing and metric instrumentation with complete network failure isolation.

### 🛡️ Human-In-The-Loop Webhook Notification Gateway (Issue #20 / ADR-0020)
- `feat(governance)`: Define decoupled `IApprovalNotifierPort` in `nexusai.brain.ports.governance_port` for outbound safety approval dispatch.
- `feat(governance)`: Introduce `WebhookApprovalNotifier` in `nexusai.infrastructure.notification` with support for Generic JSON, Slack Incoming Webhooks (Block Kit), and Discord Webhooks (Embeds).
- `feat(governance)`: Implement asynchronous write-behind (non-blocking) dispatch in `HumanApprovalEngine` with complete exception suppression so network outages never block agent loops or leak resource quotas.
- `feat(governance)`: Implement cryptographic HMAC-SHA256 signature verification (`X-NexusAI-Signature: sha256=<hex>`) and export `verify_hmac_signature` verifier.
- `feat(governance)`: Support automatic webhook format detection based on destination URL (`hooks.slack.com`, `discord.com/api/webhooks`).

### 🧠 Distributed Semantic Memory Vector Adapters (Issue #19 / ADR-0019)
- `feat(memory)`: Implement `PgVectorStore` conforming to `VectorStore` using `asyncpg` with connection pooling, automated `vector` extension and table bootstrapping, and configurable HNSW / IVFFlat indexes.
- `feat(memory)`: Implement `QdrantVectorStore` conforming to `VectorStore` using asynchronous Qdrant client, native Cosine distance HNSW indexing, and deterministic UUIDv5 point ID mapping.
- `feat(memory)`: Provide graceful in-memory/SQLite fallback when external database drivers or connections are unconfigured, ensuring zero downtime for local development.
- `feat(memory)`: Wire `PgVectorStore` and `QdrantVectorStore` into `MemoryEngineConfig` and `VectorModule.build()`.

### 🌐 Remote MCP Streaming & SSE Transport (Issue #18 / ADR-0018)
- `feat(mcp)`: Implement Server-Sent Events (SSE) and HTTP streaming transport for remote Model Context Protocol (MCP) servers conforming to the MCP 2024-11-05 specification.
- `feat(mcp)`: Establish polymorphic `BaseMcpClient` contract implemented by `McpClient` (stdio) and `McpSseClient` (SSE/HTTP) for transparent tool registration and capability discovery.
- `feat(mcp)`: Implement `McpHttpTransport` with asynchronous HTTP connection pooling via `httpx` and W3C-compliant SSE frame streaming.
- `feat(mcp)`: Introduce automatic reconnection logic with exponential backoff and proactive heartbeat liveness checks.
- `feat(mcp)`: Add remote endpoint URL, headers, and transport configuration support in `config/mcp_servers.yaml`.

### 🚀 Packaging & Architecture Governance
- `fix(core)`: Resolve Python Package Wheel Build (Gate 6) via `hatchling` and `build` dev dependencies.
- `fix(core)`: Pass 100% of full integration test suite (104/104 tests passed, 0 failures).
- `fix(architecture)`: Eliminate Rule A001 architectural technical debt by removing 28 illegal runtime imports from `nexusai.providers`, achieving 100.0% Technical Debt Score and clean boundaries.
- `fix(persistence)`: Implement process-level mutex lock (`threading.Lock()`) for SQLite memory writes to resolve table-locking contention under high concurrency.
- `fix(audit)`: Synchronize canonical SHA-256 hash payload in `AuditEvent` and `SQLiteAuditStore.verify_chain` for cryptographic tamper detection.

### 🐳 Deployment & Containerization
- `feat(deploy)`: Implement production multi-stage `Dockerfile` (Python 3.12-slim, non-root user UID 10001, security capability drop, and internal healthcheck).
- `feat(deploy)`: Add `.dockerignore` and `docker-compose.yml` for multi-container local runtime with persistent storage and Redis coordination.
- `feat(api)`: Add `/health/live`, `/health/ready`, `/healthz`, and `/readyz` probe endpoints matching Kubernetes Helm specifications.

### 📚 Documentation & Guides
- `docs(tutorials)`: Add comprehensive `docs/tutorials/running-and-testing.md` guide detailing CLI, Web UI, Docker execution, and tiered test matrices.
- `docs(readme)`: Modernize `README.md` with dedicated Running and Testing sections, updated `v1.0.0` badges, and operational scope clarification.
- `docs(learn)`: Add comprehensive `LEARN.md` step-by-step educational guide for GitHub Community Exchange / GitHub Learning Program.
- `docs(vault)`: Expand Obsidian Second Brain with `ANALISIS-TOTAL-ARSITEKTUR-NEXUSAI.md` and 4 subsystem architecture blueprints (`Brain`, `Runtime`, `Infrastructure`, `Governance`).

---

## [1.0.0] - 2026-09-02

### 🚀 Phase 7 / Level 4: Built-in MCP Server Pack & Autonomous Distributed Cluster (ADR-0014, ADR-0015, ADR-0016)
- `feat(mcp)`: Implement native Python 3.12+ Built-in MCP Server Pack running over stdio JSON-RPC 2.0 out-of-the-box without requiring external `npm` or `uvx` dependencies.
  - `FilesystemMcpServer`: Secure sandboxed workspace operations (`read_file`, `write_file`, `list_directory`, `get_file_info`, `search_files`) with strict path traversal jail boundary enforcement.
  - `SqliteMcpServer`: Non-blocking async SQLite execution (`read_query`, `write_query`, `list_tables`, `describe_table`) with parameterized query support via `aiosqlite`.
  - `WebFetcherMcpServer`: Asynchronous web page content extraction (`fetch_url`) stripping script/style tags and generic HTTP requests (`http_request`) via `httpx`.
  - `McpServerBase`: Resilient stdio JSON-RPC 2.0 base framework handling initialization, ping, tool discovery, and tool call dispatching with standard output flushing and error isolation.
- `feat(mcp)`: Auto-resolve `python` / `python3` command to active `sys.executable` and propagate process exit/stderr errors instantly in `McpClient`.
- `feat(distributed)`: Implement `DistributedWorkerPool` and `DistributedExecutionScheduler` coordinating PlanGraph DAG branches across distributed worker nodes with monotonic fencing tokens (ADR-0014).
- `feat(distributed)`: Implement `WorkerHeartbeatSupervisor` for dead node eviction and auto-recovery, `WorkerAutoScaler` for queue-based dynamic scale-out/scale-in with anti-thrashing cooldown, and `ClusterOrchestrator` unified facade (ADR-0016).
- `feat(web)`: Real-time Server-Sent Events (SSE) stream (`/api/events/stream`), REST MCP endpoints (`/api/mcp/servers`, ping, reload), and Cyber-Glassmorphism Web OS dashboard.
- `feat(test)`: Continuous soak & endurance test harness (`tools/run_soak_test.py`) tracking zero memory leak curves, GC object retention, and latency drift.
- `feat(mesh)`: Implement Multi-Agent Collaboration Mesh (`A2AMessage`, `AgentCollaborationMesh`) and specialized agents (`PlannerSpecialist`, `CoderSpecialist`, `AuditorSpecialist`, `OrchestratorSpecialist`) for multi-round consensus and review-feedback loops (ADR-0017).
- `feat(cli)`: Implement interactive Terminal UI (TUI) Live Monitor (`nexusai cluster top`, `nexusai top`, `make tui`) powered by Rich for real-time distributed cluster topology, worker loads, and auto-scaler events.
- `feat(cli)`: Interactive API key onboarding and provider auto-detection (OpenRouter, Groq, OpenAI, Ollama, DeepSeek) upon starting interactive chat shell.
- `feat(brain)`: Enable function tool-calling dispatch loop and multi-turn conversational memory integration in `BrainCoordinator`.
- `feat(release)`: Automated Release Candidate verification runner (`tools/verify_release.py`) and modernized developer `Makefile`.




---

## [0.7.0] - 2026-08-12

### 🚀 Phase 5: Production Deployment, Multi-Node Coordination & Governance
- `feat(coordination)`: Implement `PostgresExecutionCoordinator` and `RedisExecutionCoordinator` for multi-worker distributed lease coordination and monotonic fencing tokens.
- `feat(persistence)`: Implement durable PostgreSQL execution persistence, transaction boundaries, and SQLite migration pipeline.
- `feat(secrets)`: Implement HashiCorp Vault (`VaultCredentialProvider`) and AWS KMS (`KMSCredentialProvider`) credential management with automatic secret rotation.
- `feat(sandbox)`: Implement process and gRPC sandbox isolation with capability policies.
- `feat(dr)`: Implement disaster recovery, snapshot metadata, and epoch tracking.
- `feat(observability)`: Implement OpenTelemetry-compatible structured logging and Prometheus metric exporters.
- `feat(k8s)`: Implement Helm deployment manifests, non-root security contexts, read-only root filesystems, and image digest pinning support.

---

## [0.6.0] - 2026-08-07

### 🟢 Added — Phase 6: End-to-End Integration, Observability & Learning Loop
- `feat(telemetry)`: OpenTelemetry-compatible `ExecutionSpan` and `TraceCollector` capturing sub-operation timeline spans and aggregated latency breakdowns (`planner.plan`, `tool.execute`, `reflection.reflect`).
- `feat(runtime)`: Granular `ResourceManager` and `ResourceBudget` tracking CPU, RAM, token limits, concurrency worker ceilings, API cost ceilings, and raising `ResourceQuotaExceededError`.
- `feat(runtime)`: `AdaptiveBudgetAdaptation` dynamically scaling down concurrency and context depth when resource budgets run low.
- `feat(eval)`: Closed-loop `OfflineEvaluator` and `StrategyTrainer` automatically tuning `PlannerWeights` based on historical `DecisionDatasetEntry` outcomes and scalar rewards.
- `feat(memory)`: `DeduplicatingClusterCompressor` deduplicating exact/near-duplicate texts before token budget compression.

---

## [0.5.0] - 2026-08-07

### 🟢 Added — Phase 5: Modular Planner, Capability Discovery, Execution Policy & Memory Intelligence
- `feat(planner)`: Modular ExecutionPlanner pipeline stages (`GoalAnalyzer`, `TaskDecomposer`, `DependencyResolver`, `ActionRanker`, `ExecutionPlanner`) producing `PlanGraph` DAG plans.
- `feat(planner)`: Pre-execution `PlanValidator` verifying DFS cycle detection, dead-end nodes, unreachable steps, and budget bounds.
- `feat(planner)`: Parallel async `ExecutionScheduler` running independent DAG branches concurrently via worker queues.
- `feat(ports)`: Dynamic `RuntimeCapabilityDiscovery` and ephemeral `DynamicCapabilityGraphBuilder` decoupling planning from hardcoded tool names.
- `feat(runtime)`: `ExecutionPolicy` and `CircuitBreaker` sandboxing preventing cascading tool failures across `CLOSED`, `OPEN`, and `HALF_OPEN` states.
- `feat(planner)`: `PlanGraphExecutionEngine` executing DAG nodes sequentially or concurrently enforcing runtime policies.
- `feat(eval)`: `DecisionDataset` and `DecisionDatasetEntry` capturing execution decision trajectories for offline evaluation and RL training.
- `feat(memory)`: Multi-tier Memory Intelligence pipeline (`MemoryIndexer`, `MemoryRetriever`, `MemoryRanker` with exponential recency decay, `MemoryConflictResolver`, `ContextCompressor`, `ContextAssembler`, `MemoryPolicy`).
- `feat(domain)`: `WorldState` domain model encapsulating workspace path, environment variables, active MCP servers, and system resources.
- `feat(events)`: Publish-subscribe `AgentEventBus` and typed domain events (`PlannerFinishedEvent`, `ExecutionStartedEvent`, `ExecutionFinishedEvent`, `ToolFailedEvent`, `MemoryUpdatedEvent`, `DecisionRecordedEvent`).
- `feat(reflection)`: Diagnostic `ReflectionEngine` assessing expectation-outcome gaps and `PlanRepairEngine` dynamically patching `PlanGraph` DAG nodes.
- `feat(memory)`: `MemoryConsolidator` consolidating stale episodic memories into permanent semantic knowledge summaries.

---

## [0.4.0] - 2026-08-06

### 🟢 Added — Phase 4: Quality Engineering & Replay Infrastructure
- `feat(replay)`: Deterministic execution replay (`ReplayRecorder`, `ReplayRunner`, `ExecutionLog`, `ExecutionEvent`).
- `feat(state)`: Core and Extended state hash computation (`compute_core_state_hash`, `compute_extended_state_hash`).
- `feat(eval)`: Golden scenario corpus generation (`ScenarioCorpus`, `ScenarioRunner`, `AgentEvaluator`, `BenchmarkComparator`, `BenchmarkReportAggregator`).
- `feat(ci)`: Automated benchmark regression detection and CI quality gate.

---

## [0.3.0] - 2026-08-04

### 🟢 Added — Phase 3: Brain Runtime Core
- `feat(brain)`: Versioned domain contracts and runtime context infrastructure (`BrainSession`, `ExecutionContext`, `PromptBundle`, `ArtifactRegistry`).
- `feat(brain)`: Provider ExecutionPlan and Capability Negotiation Bridge (`RequiredCapabilities`, `ProviderSelector`).
- `feat(brain)`: Delta streaming execution, telemetry tracer, and Kernel Outbox transactional persistence.

---

## [0.2.0] - 2026-08-03

### 🟢 Added — Phase 2: Kernel Orchestration Engine & Quality Gate
- `feat(kernel)`: Deterministic boot, topological dependency resolution, state machine lifecycle coordination, and `KernelOrchestrator`.
- `feat(quality)`: Modular quality gate runners (`run_formatter.py`, `run_linter.py`, `run_typecheck.py`, `run_tests.py`, `run_quality_gate.py`).

---

## [0.1.0-alpha] - 2026-08-03

### 🟢 Added — Initial Alpha Release
- Core CQRS architecture (`CommandBus`, `QueryBus`, `EventBus`).
- Model-agnostic LLM provider interfaces (OpenAI, OpenRouter, Ollama, Gemini, Anthropic).
- Interactive CLI application (`nexusai chat`) and Web Dashboard.
- Security Guard and Risk Classifier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
