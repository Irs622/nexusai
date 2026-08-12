"""Capability policy enforcement engine for gRPC container sandbox execution."""

from __future__ import annotations

import re
from typing import Any, Mapping

from nexusai.brain.domain.sandbox import SandboxSpec


class CapabilityPolicyViolation(Exception):
    """Raised when a sandbox execution spec violates isolation rules."""


class CapabilityPolicyEngine:
    """Enforces strict isolation rules: rejects host path mounts, docker socket access, DB credentials, and Vault tokens."""

    FORBIDDEN_PATHS = (
        "/etc/passwd",
        "/etc/shadow",
        "/var/run/docker.sock",
        "/proc",
        "/sys",
        "/root",
    )

    FORBIDDEN_ENV_PATTERNS = (
        r".*DATABASE_URL.*",
        r".*POSTGRES.*",
        r".*VAULT_TOKEN.*",
        r".*REDIS_URL.*",
    )

    @classmethod
    def validate_spec(cls, spec: SandboxSpec) -> None:
        """Validate SandboxSpec against capability policies prior to container dispatch."""
        # 1. Check host path mounts
        for path in spec.policy.allowed_host_paths:
            for forbidden in cls.FORBIDDEN_PATHS:
                if path.startswith(forbidden):
                    raise CapabilityPolicyViolation(f"Access to forbidden host path '{path}' is DENIED!")

        # 2. Check forbidden environment variables
        for env_key in spec.ephemeral_env.keys():
            for pat in cls.FORBIDDEN_ENV_PATTERNS:
                if re.match(pat, env_key, re.IGNORECASE):
                    raise CapabilityPolicyViolation(f"Environment variable '{env_key}' leaks host credentials and is DENIED!")

        # 3. Check arguments for path traversal attempts
        args_str = str(spec.arguments)
        for forbidden in cls.FORBIDDEN_PATHS:
            if forbidden in args_str:
                raise CapabilityPolicyViolation(f"Argument attempts unauthorized host access to '{forbidden}' and is DENIED!")
