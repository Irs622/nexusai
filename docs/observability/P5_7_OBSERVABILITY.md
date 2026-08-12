# NexusAI Production Observability Architecture & Operations

```text
===================================================================================
                   P5-7 OBSERVABILITY SECURITY INVARIANT
    "OBSERVABILITY MUST NEVER CREATE, MODIFY, EXTEND, OR BYPASS EXECUTION AUTHORITY."
===================================================================================
```

## 1. Metrics & Cardinality Policy

NexusAI enforces strict Prometheus label allowlists (`tool_id`, `provider`, `operation`, `status`, `risk_level`, `sandbox_result`, `error_type`, `recovery_status`). High-cardinality values (`execution_id`, `session_id`, prompts, completions, URLs) are **FORBIDDEN** in metric attributes to prevent TSDB memory exhaustion.

---

## 2. Health & Readiness Signals

- `/health/live`: Returns `True` if HTTP process is alive.
- `/health/ready`: Returns `True` ONLY if infrastructure dependencies and disaster recovery state permit accepting traffic. If disaster recovery status is `QUARANTINED` or `FAILED`, readiness returns `ready = False`.

---

## 3. Secret Redaction Policy

Centralized recursive secret redaction masks `api_key`, `access_token`, `authorization`, `cookie`, `password`, `secret`, `bearer` before emission to metrics, spans, structured logs, or external telemetry exporters.
