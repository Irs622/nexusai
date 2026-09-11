"""Environment & Security Health Diagnostics Engine for NexusAI.

Implements 'nexusai doctor' command with 11 health checks, exit code semantics
(0 for all pass, 1 for fail, 2 for warn), formatted terminal indicators,
and machine-readable JSON output for CI/CD pipelines.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class CheckStatus(str, Enum):
    """Status of a health check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class CheckSeverity(str, Enum):
    """Severity assigned to a failure condition."""

    FAIL = "FAIL"
    WARN = "WARN"


@dataclass
class HealthCheckResult:
    """Individual health check evaluation outcome."""

    name: str
    status: CheckStatus
    detail: str
    severity: CheckSeverity = CheckSeverity.FAIL

    def to_dict(self) -> dict[str, str]:
        """Convert check result to dictionary for JSON output."""
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
        }


class DoctorEngine:
    """Diagnostic health check engine validating deployment and security configuration."""

    def __init__(
        self,
        base_dir: Path | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> None:
        """Initialize DoctorEngine with base workspace directory and env override."""
        self.base_dir = base_dir or Path.cwd()
        self.env_vars = env_vars if env_vars is not None else dict(os.environ)

    def _get_env(self, key: str, default: str | None = None) -> str | None:
        """Retrieve an environment variable from current context."""
        return self.env_vars.get(key, default)

    def check_python_version(self) -> HealthCheckResult:
        """Validate Python version >= 3.12."""
        current_tuple = sys.version_info[:2]
        version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        if current_tuple >= (3, 12):
            return HealthCheckResult(
                name="python_version",
                status=CheckStatus.PASS,
                detail=f"{version_str} (>= 3.12 required)",
                severity=CheckSeverity.FAIL,
            )
        return HealthCheckResult(
            name="python_version",
            status=CheckStatus.FAIL,
            detail=f"{version_str} is unsupported (requires Python >= 3.12)",
            severity=CheckSeverity.FAIL,
        )

    def check_config_file(self) -> tuple[HealthCheckResult, dict[str, Any]]:
        """Validate config/default.yaml exists and parses successfully."""
        cfg_path = self.base_dir / "config" / "default.yaml"
        if not cfg_path.is_file():
            return (
                HealthCheckResult(
                    name="config_file",
                    status=CheckStatus.FAIL,
                    detail=f"Configuration file not found: {cfg_path}",
                    severity=CheckSeverity.FAIL,
                ),
                {},
            )

        try:
            content = cfg_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content) or {}
            if not isinstance(parsed, dict):
                return (
                    HealthCheckResult(
                        name="config_file",
                        status=CheckStatus.FAIL,
                        detail=f"{cfg_path} must contain a YAML mapping",
                        severity=CheckSeverity.FAIL,
                    ),
                    {},
                )
            return (
                HealthCheckResult(
                    name="config_file",
                    status=CheckStatus.PASS,
                    detail=f"{cfg_path} exists and parsed successfully",
                    severity=CheckSeverity.FAIL,
                ),
                parsed,
            )
        except Exception as exc:
            return (
                HealthCheckResult(
                    name="config_file",
                    status=CheckStatus.FAIL,
                    detail=f"Failed to parse {cfg_path}: {exc}",
                    severity=CheckSeverity.FAIL,
                ),
                {},
            )

    def check_model_provider_api_key(self) -> HealthCheckResult:
        """Validate OPENAI_API_KEY or equivalent model provider key is set in env."""
        provider_keys = [
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "MOCK_PROVIDER",
            "OLLAMA_BASE_URL",
        ]
        found_keys = [k for k in provider_keys if self._get_env(k)]

        if found_keys:
            return HealthCheckResult(
                name="model_provider_api_key",
                status=CheckStatus.PASS,
                detail=f"Model provider credential configured ({', '.join(found_keys)})",
                severity=CheckSeverity.FAIL,
            )
        return HealthCheckResult(
            name="model_provider_api_key",
            status=CheckStatus.FAIL,
            detail="No model provider API key found in environment (OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY)",
            severity=CheckSeverity.FAIL,
        )

    def check_cors_config(self, default_cfg: dict[str, Any]) -> HealthCheckResult:
        """Validate CORS allowed_origins does not contain wildcard '*'."""
        api_cfg = default_cfg.get("api", {}) if isinstance(default_cfg, dict) else {}
        allowed_origins = api_cfg.get("allowed_origins", ["http://localhost:8000"])

        env_origins = self._get_env("NEXUSAI_ALLOWED_ORIGINS")
        if env_origins:
            allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

        if not isinstance(allowed_origins, list):
            allowed_origins = [str(allowed_origins)]

        has_wildcard = any(o.strip() == "*" for o in allowed_origins)

        if has_wildcard:
            return HealthCheckResult(
                name="cors_config",
                status=CheckStatus.FAIL,
                detail="allowed_origins contains wildcard '*' (insecure)",
                severity=CheckSeverity.FAIL,
            )
        return HealthCheckResult(
            name="cors_config",
            status=CheckStatus.PASS,
            detail=f"allowed_origins configured without wildcard: {allowed_origins}",
            severity=CheckSeverity.FAIL,
        )

    def check_security_strict_mode(self) -> tuple[HealthCheckResult, dict[str, Any]]:
        """Validate security.strict_mode is true."""
        sec_path = self.base_dir / "config" / "security.yaml"
        if not sec_path.is_file():
            return (
                HealthCheckResult(
                    name="security_strict_mode",
                    status=CheckStatus.FAIL,
                    detail=f"Security config file missing: {sec_path}",
                    severity=CheckSeverity.FAIL,
                ),
                {},
            )

        try:
            sec_data = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
            sec_block = sec_data.get("security", {}) if isinstance(sec_data, dict) else {}
            strict_mode = sec_block.get("strict_mode", False)

            if strict_mode is True:
                return (
                    HealthCheckResult(
                        name="security_strict_mode",
                        status=CheckStatus.PASS,
                        detail="strict_mode: true",
                        severity=CheckSeverity.FAIL,
                    ),
                    sec_block,
                )
            return (
                HealthCheckResult(
                    name="security_strict_mode",
                    status=CheckStatus.FAIL,
                    detail=f"strict_mode is {strict_mode} (must be true)",
                    severity=CheckSeverity.FAIL,
                ),
                sec_block,
            )
        except Exception as exc:
            return (
                HealthCheckResult(
                    name="security_strict_mode",
                    status=CheckStatus.FAIL,
                    detail=f"Failed to read security configuration: {exc}",
                    severity=CheckSeverity.FAIL,
                ),
                {},
            )

    def check_protected_paths(self, sec_block: dict[str, Any]) -> HealthCheckResult:
        """Validate protected_paths is not empty."""
        paths = sec_block.get("protected_paths", [])
        if isinstance(paths, list) and len(paths) > 0:
            return HealthCheckResult(
                name="protected_paths",
                status=CheckStatus.PASS,
                detail=f"{len(paths)} protected paths configured",
                severity=CheckSeverity.WARN,
            )
        return HealthCheckResult(
            name="protected_paths",
            status=CheckStatus.WARN,
            detail="protected_paths is empty",
            severity=CheckSeverity.WARN,
        )

    def check_capability_profiles(self) -> HealthCheckResult:
        """Validate capability profiles file (config/capabilities.yaml) exists."""
        cap_path = self.base_dir / "config" / "capabilities.yaml"
        if not cap_path.is_file():
            return HealthCheckResult(
                name="capability_profiles",
                status=CheckStatus.WARN,
                detail="config/capabilities.yaml not found (using built-in defaults)",
                severity=CheckSeverity.WARN,
            )

        try:
            from nexusai.security.capability import CapabilityResolver

            resolver = CapabilityResolver.from_yaml(cap_path)
            profile_names = list(resolver.profiles.keys())
            return HealthCheckResult(
                name="capability_profiles",
                status=CheckStatus.PASS,
                detail=f"configured ({len(profile_names)} profiles: {', '.join(profile_names)})",
                severity=CheckSeverity.WARN,
            )
        except Exception as exc:
            return HealthCheckResult(
                name="capability_profiles",
                status=CheckStatus.WARN,
                detail=f"config/capabilities.yaml failed to parse: {exc}",
                severity=CheckSeverity.WARN,
            )

    def check_api_authentication(self, default_cfg: dict[str, Any]) -> HealthCheckResult:
        """Validate API authentication configuration is present and enabled."""
        auth_cfg = default_cfg.get("auth", {}) if isinstance(default_cfg, dict) else {}
        is_enabled = auth_cfg.get("enabled", False)
        header = auth_cfg.get("api_key_header", "X-NexusAI-API-Key")

        if is_enabled:
            return HealthCheckResult(
                name="api_authentication",
                status=CheckStatus.PASS,
                detail=f"Authentication enabled (header: {header})",
                severity=CheckSeverity.FAIL,
            )
        return HealthCheckResult(
            name="api_authentication",
            status=CheckStatus.FAIL,
            detail="Authentication is disabled or missing in config/default.yaml",
            severity=CheckSeverity.FAIL,
        )

    def check_sandbox_binary(self) -> HealthCheckResult:
        """Validate docker or podman binary is found in PATH."""
        docker_path = shutil.which("docker")
        podman_path = shutil.which("podman")

        if docker_path:
            return HealthCheckResult(
                name="sandbox_binary",
                status=CheckStatus.PASS,
                detail=f"docker binary found at {docker_path}",
                severity=CheckSeverity.WARN,
            )
        if podman_path:
            return HealthCheckResult(
                name="sandbox_binary",
                status=CheckStatus.PASS,
                detail=f"podman binary found at {podman_path}",
                severity=CheckSeverity.WARN,
            )
        return HealthCheckResult(
            name="sandbox_binary",
            status=CheckStatus.WARN,
            detail="Neither docker nor podman found in PATH (sandbox execution unavailable)",
            severity=CheckSeverity.WARN,
        )

    def check_otlp_endpoint(self) -> HealthCheckResult:
        """Validate OTEL_EXPORTER_OTLP_ENDPOINT is set in environment."""
        otlp_endpoint = self._get_env("OTEL_EXPORTER_OTLP_ENDPOINT") or self._get_env(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
        )
        if otlp_endpoint and otlp_endpoint.strip():
            return HealthCheckResult(
                name="otlp_endpoint",
                status=CheckStatus.PASS,
                detail=f"OTEL_EXPORTER_OTLP_ENDPOINT set to {otlp_endpoint.strip()}",
                severity=CheckSeverity.WARN,
            )
        return HealthCheckResult(
            name="otlp_endpoint",
            status=CheckStatus.WARN,
            detail="OTEL_EXPORTER_OTLP_ENDPOINT not set (distributed tracing disabled)",
            severity=CheckSeverity.WARN,
        )

    def check_database(self, default_cfg: dict[str, Any]) -> HealthCheckResult:
        """Validate SQLite database directory/path is writable."""
        paths_cfg = default_cfg.get("paths", {}) if isinstance(default_cfg, dict) else {}
        storage_dir_str = paths_cfg.get("storage_dir", "storage")

        db_dir = self.base_dir / storage_dir_str
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            test_file = db_dir / ".doctor_write_probe"
            test_file.write_text("probe", encoding="utf-8")
            test_file.unlink()
            return HealthCheckResult(
                name="database",
                status=CheckStatus.PASS,
                detail=f"Database storage path is writable ({db_dir})",
                severity=CheckSeverity.FAIL,
            )
        except Exception as exc:
            return HealthCheckResult(
                name="database",
                status=CheckStatus.FAIL,
                detail=f"Database storage path {db_dir} is not writable: {exc}",
                severity=CheckSeverity.FAIL,
            )

    def run_all_checks(self) -> list[HealthCheckResult]:
        """Execute all 11 health checks in topological diagnostic order."""
        results: list[HealthCheckResult] = []

        # 1. Python version
        results.append(self.check_python_version())

        # 2. Config file
        res_cfg, default_cfg = self.check_config_file()
        results.append(res_cfg)

        # 3. Model provider API key
        results.append(self.check_model_provider_api_key())

        # 4. CORS config
        results.append(self.check_cors_config(default_cfg))

        # 5. Security strict mode
        res_sec, sec_block = self.check_security_strict_mode()
        results.append(res_sec)

        # 6. Protected paths
        results.append(self.check_protected_paths(sec_block))

        # 7. Capability profiles
        results.append(self.check_capability_profiles())

        # 8. API authentication
        results.append(self.check_api_authentication(default_cfg))

        # 9. Sandbox binary
        results.append(self.check_sandbox_binary())

        # 10. OTLP endpoint
        results.append(self.check_otlp_endpoint())

        # 11. Database
        results.append(self.check_database(default_cfg))

        return results

    @staticmethod
    def compute_summary(results: list[HealthCheckResult]) -> tuple[str, int]:
        """Compute overall status string and exit code from check results.

        Exit codes:
        - 0: All checks pass (no FAIL, no WARN)
        - 1: At least one FAIL check
        - 2: No FAIL, but at least one WARN present
        """
        has_fail = any(r.status == CheckStatus.FAIL for r in results)
        has_warn = any(r.status == CheckStatus.WARN for r in results)

        if has_fail:
            return ("FAIL", 1)
        if has_warn:
            return ("WARN", 2)
        return ("PASS", 0)

    def format_json(self, results: list[HealthCheckResult]) -> str:
        """Produce machine-readable JSON format for CI/CD integration."""
        status, _ = self.compute_summary(results)
        payload = {
            "status": status,
            "checks": [r.to_dict() for r in results],
        }
        return json.dumps(payload, indent=2)
