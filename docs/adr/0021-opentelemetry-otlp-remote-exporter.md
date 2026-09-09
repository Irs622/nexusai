# ADR 0021: OpenTelemetry OTLP Remote Exporter for Distributed Tracing and Metrics

## Status
Accepted

## Context
NexusAI operates as an enterprise-grade agentic workflow and execution engine running complex multi-turn LLM reasoning loops, tool interactions, human approvals, and background tasks. As agent workflows span multiple services, microservices, and external providers, operators require deep visibility into:
1. **Trace Propagation & Distributed Spans**: End-to-end trace correlation linking user requests, agent planning turns, tool executions, vector retrievals, and model invocations.
2. **Standardized Wire Formats**: Enterprise observability backends (e.g., SigNoz, Jaeger, Datadog, Honeycomb, Dynatrace, New Relic) natively ingest OpenTelemetry Protocol (OTLP/HTTP) payloads. Proprietary or ad-hoc telemetry logging creates vendor lock-in and impedes integration with standard enterprise APM stacks.
3. **Execution Latency & Performance Ceilings**: Synchronous metric reporting or tracing over HTTP could introduce blocking network delays into agent execution pipelines, violating strict latency budgets (< 1.0ms per turn span).
4. **Security & Data Privacy**: Execution spans frequently encounter prompt payloads, tool inputs, and environment configurations containing sensitive credentials, bearer tokens, or API keys. Sending unredacted telemetry over the wire violates security governance directives.

## Decision
We implement a fully vendor-neutral, asynchronous, write-behind OpenTelemetry OTLP exporter implementing `IObservabilityPort`:

1. **Architecture & Module Location**:
   - Implemented in `nexusai.infrastructure.observability.otel_exporter` and exposed through `nexusai.infrastructure.observability`.
   - Adheres to `IObservabilityPort` from `nexusai.brain.domain.observability`.
   - Separates trace export (`OtelTraceExporter`), metrics export (`OtelMetricsExporter`), span context management (`OtelSpanContext`), and the unified adapter (`OtelRemoteExporter`).

2. **Standard OTLP JSON Wire Format**:
   - Implements native OpenTelemetry JSON schema for trace signals (`resourceSpans`) and metric signals (`resourceMetrics`).
   - Uses W3C-compliant 16-byte (32-hex) `trace_id` and 8-byte (16-hex) `span_id`.
   - Correctly formats timestamps in nanoseconds as string-encoded 64-bit integers (`startTimeUnixNano`, `endTimeUnixNano`, `timeUnixNano`).
   - Dynamically formats attribute values into typed OTLP `AnyValue` objects (`stringValue`, `intValue`, `doubleValue`, `boolValue`, `arrayValue`, `kvlistValue`).

3. **Standard OTLP Environment Configuration**:
   - Supports standard OpenTelemetry environment variables:
     - `OTEL_EXPORTER_OTLP_ENDPOINT`: Base collector endpoint (defaults to `http://localhost:4318`), automatically appending `/v1/traces` and `/v1/metrics`.
     - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`: Signal-specific URL override for traces.
     - `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`: Signal-specific URL override for metrics.
     - `OTEL_EXPORTER_OTLP_HEADERS`: Comma-separated list of key-value authentication headers (e.g., `api-key=secret,tenant=prod`).
     - `OTEL_SERVICE_NAME`: Service identifier for resource attributes (defaults to `nexusai`).

4. **Sub-Millisecond Non-Blocking Write-Behind Queue**:
   - Spans and metric observations are enqueued into bounded in-memory FIFO buffers (`asyncio.Queue`) upon completion.
   - Enqueue latency is bounded to $< 0.05\text{ms}$ per call, well within the systemic performance ceiling of $< 1.0\text{ms}$ per turn span.
   - Bounded queues (10,000 spans, 20,000 metrics) prevent unbounded memory growth under collector downtime.
   - Flushing (`flush()`) drains buffers and dispatches chunked batches over HTTP POST via pooled `httpx.AsyncClient` connections.

5. **Security Redaction & Cardinality Controls**:
   - Automatically sanitizes span attributes and events using `sanitize_secrets_recursive()`, redacting sensitive keys (`api_key`, `token`, `secret`, `password`, `authorization`).
   - Normalizes and restricts metric attribute names using `sanitize_metric_attributes()`, stripping high-cardinality keys (`session_id`, `user_id`, `trace_id`, `prompt`, `completion`) to prevent dimensional explosions in downstream TSDBs.
   - Network timeouts, collector 4xx/5xx errors, and connectivity failures are caught, logged, and isolated without failing or disrupting agent execution.

## Alternatives Considered
- **Direct Dependency on `opentelemetry-sdk` / `opentelemetry-exporter-otlp`**: Introducing the full official OpenTelemetry Python SDK and its transitive dependencies (gRPC, proto, packaging). Rejected to keep the core NexusAI distribution lightweight, avoiding heavy binary dependencies while remaining 100% wire-compatible with standard OTLP collectors.
- **Synchronous HTTP Export**: Direct HTTP requests on span exit or metric recording. Rejected because outbound network latency (10–500ms) would degrade agent reasoning loops and introduce external failure cascades.
- **Log-Based OTLP Exporter (Stdout JSON)**: Emitting OTLP JSON to stdout for collection via Fluentbit or Vector. Supported as a complementary pattern, but insufficient for environments requiring direct remote collector push over HTTP/HTTPS.

## Consequences

### Positive
- **Instant Enterprise Compatibility**: Connects out-of-the-box to SigNoz, Jaeger, Datadog, Prometheus/OpenTelemetry Collector, and CloudWatch OTLP endpoints.
- **Zero Impact on Agent Runtime**: Write-behind queuing ensures sub-millisecond overhead ($< 0.05\text{ms}$) and complete isolation from network hiccups.
- **Hardened Security & Privacy**: Prevents accidental leakage of LLM credentials or proprietary prompt tokens into centralized telemetry backends.
- **Standard Protocol Compliance**: Full conformance to OTLP JSON v1 specifications without bulky third-party SDK dependencies.

### Negative
- **At-Least-Once Delivery & Loss Under Hard Crashes**: Unflushed queue items held in memory during an ungraceful process kill (`SIGKILL`) may be dropped unless explicitly flushed during shutdown hooks.

## Validation Criteria
- Unit tests in `tests/unit/infrastructure/observability/test_otel_exporter.py` verifying:
  - OTLP JSON payload schema structure for `resourceSpans` and `resourceMetrics`.
  - Recursive secret redaction in span attributes.
  - Metric cardinality label filtering.
  - Sub-millisecond performance budget validation ($< 1.0\text{ms}$ per span).
  - Batch export and `flush()` dispatch with mock HTTP transport.
  - Collector network failure isolation.
  - Parsing of `OTEL_EXPORTER_OTLP_HEADERS` environment strings.
- Architecture fitness verification passing with 100/100 score (`tools/run_architecture_tests.py`).
- Static analysis clean under `mypy --strict`, `ruff check`, and `black --check`.

## Review Phase
- **Implementation Phase**: Milestone 3+ Observability & Enterprise Operations.
- **Reviewers**: Observability Core Team & Architecture Guild.
