# ADR 0024: NexusAI Studio — Interactive Web Visualizer for DAG Plans and Audit Chains

## Status
Accepted

## Context
NexusAI orchestrates autonomous agent execution plans using Directed Acyclic Graphs (`PlanGraph`), cryptographic SHA-256 audit ledgers (`AuditEvent`), and governance quota bounds (`ResourceBudget`). Prior to this decision:
1. **Lack of Live Topological Visualizer**: Developers and system operators had no interactive browser interface to visualize multi-stage DAG plans, inspect node dependencies, or observe sub-100ms real-time status transitions (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`).
2. **Opaque Provenance & Cryptographic Verification**: While the backend generated cryptographically linked SHA-256 event chains, operators lacked an interactive visual audit inspector with single-click integrity verification, simulated tamper detection, and genesis reset.
3. **Absence of Governance & Human-in-the-Loop (HITL) UI**: Operator approvals for high-risk operations (e.g., container mounts, production secret access) and real-time quota consumption monitors (tool calls, tokens, cost USD, RAM) were not exposed in a unified operator console.
4. **Unified Single-Pane Experience**: The existing web console provided a simple 5-step linear graph and REPL chat, but lacked deep integration with full DAG execution templates, streaming SSE events, and security governance gates.

## Decision
We implement **NexusAI Studio** — an interactive web visualizer and operator console integrated directly with the FastAPI backend:

1. **Architecture & API Endpoints (`nexusai.api.server`)**:
   - `GET /api/v1/dag/plans`: Lists pre-configured execution plan templates (`incident_response`, `vulnerability_audit`, `data_pipeline`) with `X-NexusAI-Mode: simulation` header.
   - `GET /api/v1/dag/current`: Returns full `PlanGraph` structure including nodes, dependencies, tools, and execution outputs with `X-NexusAI-Mode: simulation` header.
   - `POST /api/v1/dag/execute` & `POST /api/v1/execute`: Triggers asynchronous DAG execution with real-time SSE broadcasts. Explicitly serves as an interactive visualization/demonstration layer returning `X-NexusAI-Mode: simulation` header.
   - `GET /api/v1/audit/events`: Returns serialized `AuditEvent` chain records with genesis linkages.
   - `POST /api/v1/audit/verify`: Verifies SHA-256 hash linkages and reports integrity status and sequence anomalies.
   - `POST /api/v1/audit/tamper`: Simulates unauthorized payload modification to demonstrate cryptographic tripwire detection.
   - `POST /api/v1/audit/reset`: Restores clean 5-event genesis audit chain.
   - `GET /api/v1/governance/budget`: Returns resource quota bounds and live usage metrics.
   - `GET /api/v1/governance/approvals`: Returns pending human-in-the-loop approval requests.
   - `POST /api/v1/governance/approvals/{approval_id}/decision`: Submits operator decisions (`APPROVED` or `DENIED`), issuing security grants and updating quotas.
   - `GET /api/events/stream` & `GET /events`: SSE event stream broadcasting `dag_step_update`, `dag_completed`, `audit_event_created`, `audit_tampered`, and `budget_updated`.

2. **Interactive SVG DAG Engine (`web/app.js`, `web/style.css`, `web/index.html`)**:
   - Displays a prominent `[DEMO MODE — Simulated Execution]` banner in `#viewDagStudio` to clearly designate the visualization harness to operators.
   - Calculates dynamic topological layering for multi-branch graphs.
   - Renders smooth cubic Bézier curves with dynamic glow and directional markers (`#arrowhead`, `#arrowhead-active`).
   - Visualizes node execution states with status badges, tool tags, and execution latency.
   - Provides an interactive node details inspector displaying step description, dependencies, and JSON output payloads.

3. **Cryptographic Audit Chain Inspector**:
   - Visual chain flow displaying SHA-256 hash provenance (`previous_event_hash` ➔ `event_hash`).
   - Real-time cryptographic verification banner displaying intact state or violation alerts.
   - Interactive tamper simulation button injecting unauthorized payload mutations to demonstrate immediate cryptographic tripwire detection.
   - Single-click genesis reset to restore verified chain baseline.

4. **Governance Quota & HITL Approval Monitor**:
   - Live visual meters for Tool Invocations, Token Consumption, Cost USD, and Memory MB.
   - Pending approvals queue with risk pills (`HIGH`, `CRITICAL`), actor details, and parameter previews.
   - Interactive `[ APPROVE ]` and `[ DENY ]` action controls with instant security grant issuance and quota synchronization.

5. **Design Aesthetics & Technology Constraints**:
   - Built exclusively with Vanilla CSS, semantic HTML5, and native JavaScript (ES2022+).
   - Adheres to the Cyber-Glass design system: dark mode (`#060910`), glassmorphism (`backdrop-filter: blur(16px)`), modern typography (`Outfit`, `JetBrains Mono`), vibrant accents (`--color-cyan`, `--color-violet`, `--color-emerald`, `--color-coral`), and zero placeholder images.

## Alternatives Considered
- **Third-Party Dashboard Frameworks (Next.js, React, TailwindCSS)**: Rejected to adhere to repository design constraints requiring lightweight, zero-node-build-step vanilla frontend architectures that run out-of-the-box via FastAPI `StaticFiles`.
- **Canvas / WebGL Graph Renderers (Cytoscape.js, D3.js)**: Evaluated, but lightweight SVG DOM rendering was chosen to allow seamless CSS styling, zero external CDN dependencies, and instant reactive state updates via Server-Sent Events.

## Consequences

### Positive
- **Complete Operational Observability**: Operators gain full visibility into autonomous execution graphs, node latencies, and output artifacts.
- **Cryptographic Trust & Auditability**: Tamper-evident SHA-256 audit ledger is directly testable and verifiable from the UI.
- **Enforced Security Boundaries**: High-risk tool calls are blocked at the governance gate until an operator confirms or denies the action.
- **Zero Build Overhead**: Runs directly from FastAPI static file mounts without npm, webpack, or external bundle steps.

### Negative
- **In-Memory State for Studio Demo**: The mock studio templates and audit chain are maintained in `app.state` for rapid interactive exploration; distributed multi-node production clusters require persistence through PostgreSQL / Transactional Outbox.
- **Simulation / Demonstration Mode Classification (Issue #29)**: The Studio DAG execution (`POST /api/v1/dag/execute`) functions as an interactive visualization and demonstration layer rather than executing actual production workloads against live external infrastructure. Step execution employs simulated delays (`asyncio.sleep(0.18)`) and synthetic telemetry for operator observation. This is explicitly surfaced via `X-NexusAI-Mode: simulation` response headers and the UI demo banner.

## Validation Criteria
- Comprehensive API test suite in `tests/unit/api/test_studio_api.py` (11/11 tests passing).
- Regression suite in `tests/unit/api/test_server_mcp_and_sse.py` (3/3 tests passing).
- Clean SVG rendering across templates (`incident_response`, `vulnerability_audit`, `data_pipeline`).
- SHA-256 cryptographic verification and tamper detection verified.
- Architectural fitness verification passing with 100/100 score (`tools/run_architecture_tests.py`).
- Static analysis clean under `ruff check`, `black --check`, and `mypy --strict`.

## Review Phase
- **Implementation Phase**: Milestone 3+ Web Studio & Observability.
- **Reviewers**: Frontend & Core Architecture Guild.
