# ADR 0020: Webhook Notification Gateway for Human-In-The-Loop Approvals

## Status
Accepted

## Context
In NexusAI, high-risk actions—such as direct filesystem mutations outside sandbox boundaries, process execution, external network calls, and system control—are governed by the `GovernanceEngine` and `HumanApprovalEngine` (established in ADR-0012 and Level-4 Safety Boundary standards). When an agent execution attempts a high-risk operation, an immutable `HumanApprovalRequest` is created with a single-use `ActionBinding` and stored in memory or persisted in `DurableApprovalStore` (SQLite/PostgreSQL).

However, prior to this decision, the approval engine was purely reactive: it waited passively for an external caller or UI polling mechanism to discover pending approvals and submit a decision. In mission-critical automated pipelines, this passive model causes:
1. **Unbounded Agent Latency**: Agents remain paused at an approval gate indefinitely until an operator manually inspects the queue.
2. **Lack of Proactive Notification**: Real-time operations teams rely on team messaging platforms (Slack, Discord) or centralized incident management webhooks (PagerDuty, custom internal endpoints) rather than polling database tables.
3. **Security Vulnerabilities in Custom Webhooks**: Unsigned webhook payloads risk spoofing and replay attacks by malicious network actors.
4. **Coupling Risks**: A synchronous webhook dispatch could deadlock the governance engine or leak resource reservations if an outbound network call experiences latency spikes or outages.

## Decision
We implement a decoupled, asynchronous, write-behind outbound notification gateway for Human-in-the-Loop approvals:

1. **Port Abstraction (`IApprovalNotifierPort`)**:
   - Defined in `nexusai.brain.ports.governance_port` to decouple approval generation from notification delivery.
   - Declares `notify_approval_required(request: HumanApprovalRequest) -> bool` and `notify_approval_resolved(request: HumanApprovalRequest, decision: HumanApprovalDecision) -> bool`.
   - Injected into `HumanApprovalEngine` as an optional dependency (`notifier: IApprovalNotifierPort | None = None`).

2. **Asynchronous Write-Behind Execution**:
   - `HumanApprovalEngine` dispatches outbound notification tasks via `asyncio.create_task()` in fire-and-forget fashion.
   - Any notification timeouts, HTTP errors, or connection resets are safely caught, logged as structured warnings, and suppressed. They **never** raise exceptions out to caller workflows, block agent execution loops, or cause resource budget leaks.

3. **Multi-Format Outbound Gateway (`WebhookApprovalNotifier`)**:
   - Implemented in `nexusai.infrastructure.notification.webhook_notifier`.
   - Supports three primary serialization formats:
     - **Generic JSON**: Structured JSON containing event metadata, risk classification, tool bindings, action digests, sanitized prompt summaries, and expiration timestamps.
     - **Slack Incoming Webhook**: Native Block Kit message format with risk badges (`CRITICAL`, `HIGH`), tool identification, and parameter fields.
     - **Discord Webhook**: Rich Embeds with color-coded severity (Red for Critical, Orange for High, Yellow for Medium, Blue for Low, Green for Approved).
   - **Automatic Platform Detection**: In `AUTO` mode, the notifier inspects the webhook URL (`hooks.slack.com` $\rightarrow$ Slack, `discord.com/api/webhooks` $\rightarrow$ Discord, otherwise Generic).

4. **Cryptographic HMAC-SHA256 Signing & Verification**:
   - Outbound requests include an `X-NexusAI-Signature: sha256=<hex>` header computed via HMAC-SHA256 over raw request bytes when a signing secret is configured.
   - Built-in verifier `verify_hmac_signature(payload_bytes, signature_header, signing_key)` is exported to allow receiving gateways and webhooks to guarantee payload authenticity and tamper-resistance.

## Alternatives Considered
- **Synchronous HTTP Dispatch**: Calling HTTP webhooks directly inside `request_approval()` before returning. Rejected because network latency or downstream service outages would directly degrade agent execution throughput and risk timing out client requests.
- **Message Broker Integration (RabbitMQ / Kafka)**: Routing notifications through an external message broker. Rejected as an immediate dependency because it introduces heavy operational overhead for local and embedded use cases. Webhooks offer direct integration with modern operational stacks (Slack, Discord, PagerDuty, Webhook gateways) with zero broker dependencies.
- **Polling via Webhook Workers**: Having a background thread poll `DurableApprovalStore`. Rejected because event-driven write-behind notifications have sub-millisecond dispatch latency compared to periodic polling intervals.

## Consequences

### Positive
- **Instant Operator Alerting**: Real-time notifications arrive in Slack, Discord, or internal dashboards within milliseconds of an approval barrier being reached.
- **Zero Engine Disruption**: Network failures, slow webhook endpoints, or timeout errors have zero impact on the safety governance state machine.
- **Vendor-Neutral Compatibility**: Teams can route notifications to standard chat platforms or enterprise HTTP endpoints without writing custom glue code.
- **Tamper-Resistant Security**: HMAC-SHA256 signatures ensure that webhook consumers can verify payload origin and integrity.

### Negative
- **At-Least-Once Delivery Semantics**: Under extreme network partitioning, webhook retries may deliver duplicate notifications to chat channels. (Idempotency is maintained via immutable `approval_id` references).

## Validation Criteria
- Unit test suite in `tests/unit/brain/test_human_approval.py` verifying that `HumanApprovalEngine` dispatches notifications asynchronously without blocking and gracefully handles notifier failures.
- Unit test suite in `tests/unit/infrastructure/test_webhook_approval_notifier.py` verifying Generic, Slack, and Discord serialization, URL auto-detection, HMAC signature generation/verification, and retry backoff.
- Multi-dimensional architecture score remains 100/100 (`tools/run_architecture_tests.py`) with zero rule violations.
- Static analysis clean under `mypy --strict`, `ruff check`, and `black --check`.

## Review Phase
- **Implementation Phase**: Milestone 3+ Governance & Safety Boundary Hardening.
- **Reviewers**: Architecture & Governance Core Teams.
