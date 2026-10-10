# API Rate Limiting in Multi-Worker Deployments

`ApiKeyService` enforces a per-key sliding window (`rate_limit_per_minute`, default 100) through a pluggable `IRateLimiter` (`nexusai.security.rate_limiter`).

| Backend | Selected when | Scope |
|---|---|---|
| `InMemoryRateLimiter` | No Redis URL configured | **Process-local.** Each uvicorn worker, pod, or replica counts independently, so the aggregate limit is about N × the configured value. Counters reset on restart. Logs a warning when `NEXUSAI_ENV=production` or `NEXUSAI_REPLICAS > 1`. |
| `RedisRateLimiter` | `NEXUSAI_REDIS_URL` or `REDIS_URL` is set | **Shared.** It uses an atomic sorted-set window (MULTI/EXEC) in Redis, so all workers and replicas enforce one aggregate limit and state survives restarts. |

## Setup

```bash
pip install "nexusai[redis]"
export NEXUSAI_REDIS_URL=redis://redis:6379/0
```

`docker-compose.yml` already sets `REDIS_URL`, so the bundled stack uses the shared limiter. For Helm, provide the same variable (see `values-production.yaml`, `redis-url` secret).

## Failure behavior

If Redis is unreachable, `RedisRateLimiter` **fails open** by default: requests are allowed and each failure is logged at `ERROR` level, so a cache outage does not lock out every client. Construct it with `fail_open=False` to reject requests instead.

## Verification

- `tests/unit/security/test_rate_limiter.py` covers:
  - two replicas sharing one backend enforce a single aggregate limit
  - concurrent acquisitions never exceed the limit
  - outage behavior
- Set `NEXUSAI_TEST_REDIS_URL` to run the live-Redis test (`-m network`).
