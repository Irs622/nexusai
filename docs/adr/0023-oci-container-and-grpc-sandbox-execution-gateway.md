# ADR 0023: OCI Container & gRPC MicroVM Sandbox Execution Gateway

## Status
Accepted

## Context
In NexusAI, agents execute dynamic workflows that involve invoking arbitrary tool commands, shell scripts, filesystem modifications, and data processing operations. Prior to this decision:
1. **Host-Level Contamination Risks**: Running tools directly on the host operating system risks accidental or malicious tampering with sensitive host configuration files (`/etc/passwd`, `/etc/shadow`), system directories (`/proc`, `/sys`), or container orchestration sockets (`/var/run/docker.sock`, `/run/containerd/containerd.sock`).
2. **Host Credential Leakage**: Child processes inherited host environment variables, risking exposure of critical database URLs (`DATABASE_URL`, `POSTGRES`), token stores (`VAULT_TOKEN`), or cloud credentials.
3. **Resource Starvation & Fork Bombs**: Unbounded tool executions could consume unlimited host CPU and memory or spawn excessive processes without strict container cgroup limits.
4. **Decoupled Architecture for Multi-Tenant Clusters**: In distributed deployment topologies, execution sandboxes must be callable remotely over asynchronous network gateways (gRPC/TCP) to separate agent planning brains from worker execution jails.

## Decision
We implement a decoupled OCI container execution gateway and asynchronous gRPC/TCP daemon implementing `ISandboxExecutionPort`:

1. **Architecture & Module Location**:
   - Resides in `nexusai.infrastructure.sandbox` and exposed via `nexusai.infrastructure.sandbox.__init__`.
   - Adheres to `ISandboxExecutionPort` from `nexusai.brain.ports.sandbox_execution_port`.
   - Separates policy validation (`CapabilityPolicyEngine`), low-level OCI command construction (`OciContainerRuntime`), execution strategy orchestration (`ContainerRuntimeEngine`), gateway daemon (`GRPCSandboxServer`), and client adapter (`GRPCSandboxClient`).

2. **OCI Container Isolation & Defense-in-Depth (`OciContainerRuntime`)**:
   - Generates hardened container execution commands for Docker, Podman, or gVisor (`runsc`):
     - `--name nexusai-sandbox-{execution_id}` with `--rm` for automated ephemeral cleanup.
     - `--read-only`: Enforces read-only root filesystems.
     - `--network=none`: Disables network egress when `policy.allow_network_egress` is False.
     - `--user 10001:10001`: Enforces non-root user execution.
     - `--cap-drop=ALL`: Drops all Linux kernel capabilities (granting only explicit `allowed_capabilities`).
     - Strict resource bounds: `--cpus`, `-m` (memory limit), `--pids-limit` (PID containment).
     - Volume isolation: Read-only mounts strictly restricted to `allowed_host_paths`.
     - Environment sanitization: Strips and redacts sensitive host credentials matching forbidden patterns.

3. **Capability Policy & Volume Jail Containment (`CapabilityPolicyEngine`)**:
   - Denies access to sensitive host paths and orchestration sockets (`/var/run/docker.sock`, `/run/containerd/containerd.sock`, `/etc/passwd`, etc.).
   - Path containment verifier (`validate_mount_paths`) validates resolved paths against allowed host directories to detect symlink escapes and directory traversals (`..`).
   - Automatically redacts credential keys (`DATABASE_URL`, `POSTGRES`, `VAULT_TOKEN`, `REDIS_URL`, `AWS_SECRET_ACCESS_KEY`, `API_KEY`) via `sanitize_ephemeral_env()`.

4. **Resource Bounds & Timeout Cleanup**:
   - Enforces execution timeouts via `asyncio.wait_for(...)`.
   - On timeout: Immediately triggers `kill_container(execution_id)` (`docker kill nexusai-sandbox-{execution_id}`) to terminate execution and clean up resources, returning `SandboxResult` with `exit_code=124` and zero orphaned container instances.

5. **Asynchronous gRPC / TCP Gateway Daemon & Client**:
   - `GRPCSandboxServer`: Implements a framed async TCP server daemon (`start(host, port)` and `stop()`) using length-prefixed JSON payloads, supporting remote distributed worker execution.
   - `GRPCSandboxClient`: Implements `ISandboxExecutionPort` with network dispatch to `target_address` over TCP framing with automatic fallback to local execution if the network daemon is offline, ensuring zero downtime in standalone/test environments.

## Alternatives Considered
- **Direct Python `subprocess.Popen` without Containerization**: Faster startup for local development, but lacks cgroup limits, PID isolation, read-only rootfs, and capability dropping required for untrusted multi-tenant code execution.
- **External Third-Party Sandboxing Services**: (e.g. AWS Lambda, Modal, or E2B). Rejected as hard core dependencies to preserve self-hosted, offline, and air-gapped deployment capabilities for NexusAI.

## Consequences

### Positive
- **True Defense-in-Depth**: Code executed by agent tools cannot access host Docker sockets or unauthorized directories.
- **Strict Resource Clamping**: Containers are bounded by cgroups (CPU, memory, max PIDs), preventing system denial-of-service.
- **Zero Orphaned Containers**: Bounded execution with explicit termination guarantees clean teardown on exit code 124.
- **Flexible Deployment**: Supports local in-process execution, local Docker/Podman, and distributed network daemon topologies over gRPC/TCP.

### Negative
- **Container Startup Latency**: Starting cold containers incurs slight overhead (~100–500ms for Docker run) compared to raw in-process execution. (Mitigated by rootless containers, pre-pulled images, and fast-path isolation).

## Validation Criteria
- Unit test suite in `tests/unit/infrastructure/sandbox/test_container_sandbox_gateway.py` verifying:
  - OCI argument construction with all security flags.
  - Capability policy credential sanitization.
  - Path jail containment validation.
  - Timeout termination with exit code 124.
  - Network TCP daemon execution and graceful shutdown.
  - Client fallback when network server is offline.
- Existing security and contract tests passing:
  - `tests/security/test_p5_5_process_isolation.py` (4/4 passed).
  - `tests/integration/test_p5_5_grpc_sandbox.py` (1/1 passed).
  - `tests/contracts/test_sandbox_execution_contract.py` (1/1 passed).
- Architecture fitness verification passing with 100/100 score (`tools/run_architecture_tests.py`).
- Static analysis clean under `mypy --strict`, `ruff check`, and `black --check`.

## Review Phase
- **Implementation Phase**: Milestone 3+ Security & Sandbox Isolation Hardening.
- **Reviewers**: Security Core Team & Infrastructure Guild.
