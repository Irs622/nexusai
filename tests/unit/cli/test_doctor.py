"""Unit tests for 'nexusai doctor' command and diagnostic engine (Issue #27)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from nexusai.cli.app import app
from nexusai.cli.doctor import CheckStatus, DoctorEngine

runner = CliRunner()


def _setup_valid_workspace(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Helper to populate a fully valid workspace for DoctorEngine."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # 1. config/default.yaml
    default_yaml = """
app:
  name: "NexusAI"
paths:
  storage_dir: "storage"
api:
  allowed_origins:
    - "http://localhost:8000"
auth:
  enabled: true
  api_key_header: "X-NexusAI-API-Key"
"""
    (config_dir / "default.yaml").write_text(default_yaml, encoding="utf-8")

    # 2. config/security.yaml
    sec_yaml = """
security:
  strict_mode: true
  protected_paths:
    - "/System"
    - "~/.ssh"
"""
    (config_dir / "security.yaml").write_text(sec_yaml, encoding="utf-8")

    # 3. config/capabilities.yaml
    cap_yaml = """
profiles:
  default:
    capabilities:
      - domain: "*"
        action: "*"
        resource: "*"
"""
    (config_dir / "capabilities.yaml").write_text(cap_yaml, encoding="utf-8")

    env_vars = {
        "OPENAI_API_KEY": "sk-test-mock-key-12345",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    }

    return tmp_path, env_vars


@pytest.mark.unit
def test_doctor_all_checks_pass(tmp_path: Path) -> None:
    """Verify exit code 0 and PASS status when all 11 checks satisfy requirements."""
    workspace, env = _setup_valid_workspace(tmp_path)

    with patch("shutil.which", return_value="/usr/bin/docker"):
        engine = DoctorEngine(base_dir=workspace, env_vars=env)
        results = engine.run_all_checks()
        status, exit_code = engine.compute_summary(results)

        assert status == "PASS"
        assert exit_code == 0
        assert len(results) == 11
        for res in results:
            assert res.status == CheckStatus.PASS


@pytest.mark.unit
def test_doctor_strict_mode_false_triggers_fail(tmp_path: Path) -> None:
    """Verify strict_mode: false triggers status FAIL and exit code 1."""
    workspace, env = _setup_valid_workspace(tmp_path)

    sec_yaml = """
security:
  strict_mode: false
  protected_paths:
    - "/System"
"""
    (workspace / "config" / "security.yaml").write_text(sec_yaml, encoding="utf-8")

    with patch("shutil.which", return_value="/usr/bin/docker"):
        engine = DoctorEngine(base_dir=workspace, env_vars=env)
        results = engine.run_all_checks()
        status, exit_code = engine.compute_summary(results)

        assert status == "FAIL"
        assert exit_code == 1
        sec_res = next(r for r in results if r.name == "security_strict_mode")
        assert sec_res.status == CheckStatus.FAIL
        assert "must be true" in sec_res.detail


@pytest.mark.unit
def test_doctor_missing_config_file_triggers_fail(tmp_path: Path) -> None:
    """Verify missing config/default.yaml triggers status FAIL with descriptive message."""
    workspace, env = _setup_valid_workspace(tmp_path)
    (workspace / "config" / "default.yaml").unlink()

    engine = DoctorEngine(base_dir=workspace, env_vars=env)
    results = engine.run_all_checks()
    status, exit_code = engine.compute_summary(results)

    assert status == "FAIL"
    assert exit_code == 1
    cfg_res = next(r for r in results if r.name == "config_file")
    assert cfg_res.status == CheckStatus.FAIL
    assert "not found" in cfg_res.detail.lower()


@pytest.mark.unit
def test_doctor_cors_wildcard_triggers_fail(tmp_path: Path) -> None:
    """Verify CORS wildcard '*' triggers status FAIL and exit code 1."""
    workspace, env = _setup_valid_workspace(tmp_path)

    default_yaml = """
app:
  name: "NexusAI"
api:
  allowed_origins:
    - "*"
auth:
  enabled: true
"""
    (workspace / "config" / "default.yaml").write_text(default_yaml, encoding="utf-8")

    engine = DoctorEngine(base_dir=workspace, env_vars=env)
    results = engine.run_all_checks()
    status, exit_code = engine.compute_summary(results)

    assert status == "FAIL"
    assert exit_code == 1
    cors_res = next(r for r in results if r.name == "cors_config")
    assert cors_res.status == CheckStatus.FAIL
    assert "wildcard" in cors_res.detail.lower()


@pytest.mark.unit
def test_doctor_missing_model_api_key_triggers_fail(tmp_path: Path) -> None:
    """Verify missing model provider key in environment triggers FAIL."""
    workspace, _ = _setup_valid_workspace(tmp_path)
    empty_env: dict[str, str] = {}

    engine = DoctorEngine(base_dir=workspace, env_vars=empty_env)
    results = engine.run_all_checks()
    status, exit_code = engine.compute_summary(results)

    assert status == "FAIL"
    assert exit_code == 1
    key_res = next(r for r in results if r.name == "model_provider_api_key")
    assert key_res.status == CheckStatus.FAIL


@pytest.mark.unit
def test_doctor_disabled_auth_triggers_fail(tmp_path: Path) -> None:
    """Verify disabled or missing auth triggers FAIL."""
    workspace, env = _setup_valid_workspace(tmp_path)

    default_yaml = """
app:
  name: "NexusAI"
auth:
  enabled: false
"""
    (workspace / "config" / "default.yaml").write_text(default_yaml, encoding="utf-8")

    engine = DoctorEngine(base_dir=workspace, env_vars=env)
    results = engine.run_all_checks()
    status, exit_code = engine.compute_summary(results)

    assert status == "FAIL"
    assert exit_code == 1
    auth_res = next(r for r in results if r.name == "api_authentication")
    assert auth_res.status == CheckStatus.FAIL


@pytest.mark.unit
def test_doctor_warnings_trigger_exit_2(tmp_path: Path) -> None:
    """Verify exit code 2 when only non-critical warnings are present (no FAIL)."""
    workspace, env = _setup_valid_workspace(tmp_path)

    # Empty protected paths (triggers WARN) and remove OTLP endpoint (triggers WARN)
    sec_yaml = """
security:
  strict_mode: true
  protected_paths: []
"""
    (workspace / "config" / "security.yaml").write_text(sec_yaml, encoding="utf-8")
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    # Missing sandbox binary (triggers WARN)
    with patch("shutil.which", return_value=None):
        engine = DoctorEngine(base_dir=workspace, env_vars=env)
        results = engine.run_all_checks()
        status, exit_code = engine.compute_summary(results)

        assert status == "WARN"
        assert exit_code == 2

        # Check that warnings triggered
        warns = [r for r in results if r.status == CheckStatus.WARN]
        assert len(warns) >= 2
        assert any(r.name == "sandbox_binary" for r in warns)
        assert any(r.name == "protected_paths" for r in warns)
        assert any(r.name == "otlp_endpoint" for r in warns)


@pytest.mark.unit
def test_doctor_missing_capabilities_file_triggers_warn(tmp_path: Path) -> None:
    """Verify missing capabilities.yaml triggers WARN (built-in fallback)."""
    workspace, env = _setup_valid_workspace(tmp_path)
    (workspace / "config" / "capabilities.yaml").unlink()

    engine = DoctorEngine(base_dir=workspace, env_vars=env)
    cap_res = engine.check_capability_profiles()

    assert cap_res.status == CheckStatus.WARN
    assert "not found" in cap_res.detail.lower()


@pytest.mark.unit
def test_doctor_format_json_structure(tmp_path: Path) -> None:
    """Verify --format json outputs machine-readable schema compliant with specifications."""
    workspace, env = _setup_valid_workspace(tmp_path)

    with patch("shutil.which", return_value="/usr/bin/docker"):
        engine = DoctorEngine(base_dir=workspace, env_vars=env)
        results = engine.run_all_checks()
        json_output = engine.format_json(results)

        data = json.loads(json_output)
        assert "status" in data
        assert data["status"] == "PASS"
        assert "checks" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) == 11

        first_check = data["checks"][0]
        assert "name" in first_check
        assert "status" in first_check
        assert "detail" in first_check


@pytest.mark.unit
def test_doctor_cli_command_json_and_text() -> None:
    """Verify Typer CLI invocation for both text and JSON formats."""
    # Run with json format
    res_json = runner.invoke(app, ["doctor", "--format", "json"])
    assert res_json.output.strip().startswith("{")
    assert res_json.output.strip().endswith("}")
    data = json.loads(res_json.output)
    assert "checks" in data

    # Run with text format
    res_text = runner.invoke(app, ["doctor", "--format", "text"])
    assert "NexusAI Environment & Security Diagnostics" in res_text.output
    assert "Python Version" in res_text.output
