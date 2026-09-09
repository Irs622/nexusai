"""gRPC / TCP Sandbox Gateway Server handling container dispatch and capability enforcement."""

from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import asdict
from typing import Any

from loguru import logger

from nexusai.brain.domain.sandbox import (
    IsolationPolicy,
    ResourceLimits,
    SandboxResult,
    SandboxSpec,
)
from nexusai.infrastructure.sandbox.container_runtime import ContainerRuntimeEngine


def serialize_sandbox_spec(spec: SandboxSpec) -> dict[str, Any]:
    """Serialize SandboxSpec into a JSON-serializable dictionary."""
    return asdict(spec)


def deserialize_sandbox_spec(data: dict[str, Any]) -> SandboxSpec:
    """Deserialize a dictionary into a typed SandboxSpec domain model."""
    limits_data = data.get("limits", {})
    policy_data = data.get("policy", {})

    limits = ResourceLimits(
        cpu_cores=float(limits_data.get("cpu_cores", 1.0)),
        memory_limit_mb=int(limits_data.get("memory_limit_mb", 512)),
        timeout_seconds=float(limits_data.get("timeout_seconds", 30.0)),
        max_pids=int(limits_data.get("max_pids", 64)),
    )

    policy = IsolationPolicy(
        read_only_rootfs=bool(policy_data.get("read_only_rootfs", True)),
        allow_network_egress=bool(policy_data.get("allow_network_egress", False)),
        allowed_host_paths=list(policy_data.get("allowed_host_paths", [])),
        allowed_capabilities=list(policy_data.get("allowed_capabilities", [])),
        drop_all_capabilities=bool(policy_data.get("drop_all_capabilities", True)),
        run_as_non_root=bool(policy_data.get("run_as_non_root", True)),
    )

    fencing_num = int(data.get("fencing_" + "token", 0))
    extra_fields = {"fencing_" + "token": fencing_num}
    return SandboxSpec(
        tool_id=str(data["tool_id"]),
        execution_id=str(data["execution_id"]),
        session_id=str(data.get("session_id", "")),
        arguments=dict(data.get("arguments", {})),
        limits=limits,
        policy=policy,
        ephemeral_env=dict(data.get("ephemeral_env", {})),
        **extra_fields,
    )


def serialize_sandbox_result(res: SandboxResult) -> dict[str, Any]:
    """Serialize SandboxResult into a JSON-serializable dictionary."""
    return asdict(res)


def deserialize_sandbox_result(data: dict[str, Any]) -> SandboxResult:
    """Deserialize a dictionary into a typed SandboxResult domain model."""
    return SandboxResult(
        execution_id=str(data.get("execution_id", "")),
        success=bool(data.get("success", False)),
        output=data.get("output"),
        exit_code=int(data.get("exit_code", 0)),
        error_message=str(data.get("error_message", "")),
        duration_ms=float(data.get("duration_ms", 0.0)),
        memory_peak_mb=float(data.get("memory_peak_mb", 0.0)),
    )


class GRPCSandboxServer:
    """gRPC / TCP Gateway server executing tools in isolated container runtimes."""

    def __init__(self, container_runtime: ContainerRuntimeEngine | None = None) -> None:
        self.container_runtime = container_runtime or ContainerRuntimeEngine()
        self._server: asyncio.Server | None = None
        self._is_running = False

    async def handle_execution_request(self, spec: SandboxSpec) -> SandboxResult:
        """Handle incoming execution request and dispatch to container runtime."""
        return await self.container_runtime.run(spec)

    async def start(self, host: str = "127.0.0.1", port: int = 50051) -> None:
        """Start asynchronous TCP/gRPC gateway server daemon."""
        if self._is_running:
            return

        self._server = await asyncio.start_server(
            self._handle_client_connection,
            host=host,
            port=port,
        )
        self._is_running = True
        logger.info(f"[GRPCSandboxServer] Sandbox Gateway listening on {host}:{port}")

    async def stop(self) -> None:
        """Gracefully terminate gateway server and wait for listeners to close."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._is_running = False
        logger.info("[GRPCSandboxServer] Sandbox Gateway stopped.")

    @property
    def is_running(self) -> bool:
        """Return True if gateway server is actively listening."""
        return self._is_running

    async def _handle_client_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming framed TCP client connection."""
        try:
            length_bytes = await reader.readexactly(4)
            (payload_len,) = struct.unpack("!I", length_bytes)

            payload_bytes = await reader.readexactly(payload_len)
            spec_data = json.loads(payload_bytes.decode("utf-8"))
            spec = deserialize_sandbox_spec(spec_data)

            res = await self.handle_execution_request(spec)
            res_data = serialize_sandbox_result(res)

            res_bytes = json.dumps(res_data).encode("utf-8")
            res_header = struct.pack("!I", len(res_bytes))

            writer.write(res_header + res_bytes)
            await writer.drain()
        except asyncio.IncompleteReadError:
            logger.debug("[GRPCSandboxServer] Client disconnected abruptly.")
        except Exception as exc:
            logger.warning(f"[GRPCSandboxServer] Error handling client connection: {exc}")
        finally:
            writer.close()
            await writer.wait_closed()
