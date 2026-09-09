"""Capability policy enforcement engine for gRPC container sandbox execution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Sequence

from nexusai.brain.domain.sandbox import SandboxSpec


class CapabilityPolicyViolation(Exception):
    """Raised when a sandbox execution spec violates isolation rules."""


class CapabilityPolicyEngine:
    """Enforces strict isolation rules: rejects host path mounts, docker socket access, DB credentials, and Vault tokens."""

    FORBIDDEN_PATHS = (
        "/etc/passwd",
        "/etc/shadow",
        "/var/run/docker.sock",
        "/run/containerd/containerd.sock",
        "/var/run/containerd/containerd.sock",
        "/var/run/crio/crio.sock",
        "/proc",
        "/sys",
        "/root",
    )

    FORBIDDEN_ENV_PATTERNS = (
        r".*DATABASE_URL.*",
        r".*POSTGRES.*",
        r".*VAULT_TOKEN.*",
        r".*REDIS_URL.*",
        r".*AWS_SECRET.*",
        r".*API_KEY.*",
    )

    @classmethod
    def sanitize_ephemeral_env(cls, env: Mapping[str, str]) -> dict[str, str]:
        """Redact sensitive host credentials from ephemeral environment variables."""
        sanitized: dict[str, str] = {}
        for k, v in env.items():
            is_forbidden = any(
                re.match(pat, k, re.IGNORECASE) for pat in cls.FORBIDDEN_ENV_PATTERNS
            )
            if not is_forbidden:
                sanitized[k] = v
        return sanitized

    @classmethod
    def validate_mount_paths(cls, allowed_host_paths: Sequence[str], requested_path: str) -> bool:
        """Verify that requested_path is contained within allowed_host_paths without traversal escapes."""
        for forbidden in cls.FORBIDDEN_PATHS:
            if requested_path.startswith(forbidden):
                return False

        req_resolved = Path(requested_path).resolve()
        for allowed in allowed_host_paths:
            allowed_resolved = Path(allowed).resolve()
            if req_resolved == allowed_resolved or allowed_resolved in req_resolved.parents:
                return True
        return False

    @classmethod
    def validate_spec(cls, spec: SandboxSpec) -> None:
        """Validate SandboxSpec against capability policies prior to container dispatch."""
        # 1. Check host path mounts
        for path in spec.policy.allowed_host_paths:
            for forbidden in cls.FORBIDDEN_PATHS:
                if path.startswith(forbidden):
                    raise CapabilityPolicyViolation(
                        f"Access to forbidden host path '{path}' is DENIED!"
                    )

        # 2. Check forbidden environment variables
        for env_key in spec.ephemeral_env.keys():
            for pat in cls.FORBIDDEN_ENV_PATTERNS:
                if re.match(pat, env_key, re.IGNORECASE):
                    raise CapabilityPolicyViolation(
                        f"Environment variable '{env_key}' leaks host credentials and is DENIED!"
                    )

        # 3. Check arguments for path traversal attempts
        args_str = str(spec.arguments)
        for forbidden in cls.FORBIDDEN_PATHS:
            if forbidden in args_str:
                raise CapabilityPolicyViolation(
                    f"Argument attempts unauthorized host access to '{forbidden}' and is DENIED!"
                )
