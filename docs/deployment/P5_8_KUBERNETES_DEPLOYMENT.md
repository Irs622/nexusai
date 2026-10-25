# NexusAI Kubernetes Deployment Architecture & Production Security Guide

```text
===================================================================================
                   P5-8 KUBERNETES SECURITY INVARIANT
   "Kubernetes MAY provide process scheduling, service discovery, networking,
   resource isolation, health management, and deployment orchestration, BUT
    Kubernetes MUST NEVER create, modify, extend, or bypass NexusAI execution authority."
===================================================================================
```

## 1. Architectural Architecture & Pod Security

Every container in the NexusAI Kubernetes Helm Chart (`deploy/helm/nexusai`) adheres to the **Restricted Pod Security Standard**:

- `runAsNonRoot: true` (`runAsUser: 10001`)
- `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true`
- `capabilities: drop: ["ALL"]`
- `seccompProfile: type: RuntimeDefault`
- ZERO `privileged`, `hostPID`, `hostNetwork`, `hostIPC`, or host socket mounts!

---

## 2. NetworkPolicies (Default-Deny Ingress & Egress)

```text
Internet Ingress ──► Control-Plane Pods ──► PostgreSQL / Redis / Vault / OTEL
                                │
                                ▼
                       Execution Worker Pods
                                │
                                ▼
                     gRPC Sandbox Gateway Pods
                     (Egress Default DENIED!)
```

---

The chart also ships `nexusai-control-plane-allow`. It admits TCP 8080 to the control plane (optionally restricted with `networkPolicy.controlPlane.ingressFrom`) and allows egress to DNS plus `networkPolicy.controlPlane.egressPorts` (default 443, 6379, 5432). Without it, the default-deny policy would make the Service unreachable and block calls to LLM providers and Redis.

---

## 3. Deployment Validation Classification

- **Static Validation**: `helm lint` passes. Rendered manifests validate with `kubeconform -strict` against Kubernetes 1.30 for default values, `values-production.yaml`, persistence disabled, an existing claim, and worker/sandbox enabled. `tests/integration/test_p5_8_kubernetes_deployment.py` renders the chart when `helm` is installed. Before 2026-10-25 the chart did not render `env`, volumes, a PVC or a Service, and the sandbox manifest was schema-invalid.
- **Read-only boot check**: The API was booted locally with a read-only working directory and `HOME`, using only the writable paths the chart mounts. `/health/live` and `/health/ready` returned 200. The nonce store was in-memory for this check because no Redis was available. This is a simulation, not a container run.
- **Security Invariant Verification**: PASS (35/35 Security Invariants verified).
- **Cluster Deployment Status**: **NOT VALIDATED ON A LIVE CLUSTER.** No image is published by the release workflow yet.

---

## 4. Installing the Chart

1. Create the credentials Secret. `NEXUSAI_ENV=production` refuses to start without an admin key, an approval secret, and a distributed nonce store:

   ```bash
   kubectl create secret generic nexusai-secrets \
     --from-literal=admin-api-key="$(openssl rand -hex 32)" \
     --from-literal=approval-secret="$(openssl rand -hex 32)" \
     --from-literal=redis-url="redis://redis:6379/0" \
     --from-literal=openrouter-api-key="..."
   ```

   The mapping from Secret keys to environment variables is `secretEnv` in `values.yaml`. Provider keys are optional (`secrets.optionalKeys`).

2. Install:

   ```bash
   helm install nexusai deploy/helm/nexusai -f deploy/helm/nexusai/values-production.yaml
   ```

### Writable paths under `readOnlyRootFilesystem`

| Mount | Volume | Contents |
|---|---|---|
| `persistence.mountPath` (`/data`) | PVC `<release>-data` (or `emptyDir` when `persistence.enabled=false`) | `execution.db`, `coordinator.db`, `api_keys.json`. The paths are injected as `NEXUSAI_EXECUTION_DB`, `NEXUSAI_COORDINATOR_DB` and `NEXUSAI_KEY_STORAGE_PATH`. |
| `/tmp` | `emptyDir` (`tmpSizeLimit`) | Temporary files (`TMPDIR`). |
| `/app/logs` | `emptyDir` (`logsSizeLimit`) | Optional file log sinks. |

The PVC carries `helm.sh/resource-policy: keep`, so `helm uninstall` does not delete data. With persistence enabled the control plane uses the `Recreate` strategy, because a `ReadWriteOnce` volume cannot attach to two pods during a rolling update.

### Current limitations

- **Single control-plane replica.** Execution and coordinator state is SQLite in WAL mode, which is unsafe on network filesystems. Rendering fails when `replicaCount.controlPlane > 1`, unless `persistence.allowSharedSqlite=true` is set explicitly.
- **Worker and sandbox are disabled by default.** The image has no dedicated worker or sandbox-gateway entrypoint. Enabling either requires `worker.command` / `sandbox.command`, and the chart refuses to render without one.
- **Readiness is static.** `/health/ready` does not yet check databases or Redis.
