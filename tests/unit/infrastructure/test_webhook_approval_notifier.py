"""Unit test suite for WebhookApprovalNotifier, payload formatting, HMAC verification, and failure isolation."""

from __future__ import annotations

import json
import pytest
import httpx

from nexusai.brain.domain.governance import ToolCapability
from nexusai.brain.domain.human_approval import (
    ActionBinding,
    ApprovalStatus,
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.infrastructure.notification.webhook_notifier import (
    WebhookApprovalNotifier,
    WebhookFormat,
    _format_discord_payload,
    _format_generic_payload,
    _format_slack_payload,
    compute_hmac_signature,
    verify_hmac_signature,
)


def _make_sample_request(
    risk_level: RiskLevel = RiskLevel.HIGH,
) -> HumanApprovalRequest:
    binding = ActionBinding(
        session_id="session-42",
        execution_id="exec-101",
        plan_fingerprint="fingerprint-abc",
        node_id="node-write-file",
        tool_id="filesystem_tool",
        tool_version="1.0.0",
        requested_capabilities=frozenset({ToolCapability.FILE_WRITE}),
        resource_scope="/app/data",
    )
    return HumanApprovalRequest(
        approval_id="app-42",
        binding=binding,
        risk_level=risk_level,
        prompt_summary="Overwrite configuration file /app/data/prod.yaml",
        metadata={"target_env": "production"},
    )


def test_generic_payload_format() -> None:
    """Test standard generic JSON webhook formatting."""
    req = _make_sample_request(RiskLevel.HIGH)
    payload = _format_generic_payload(req, event_type="approval.requested")

    assert payload["event_type"] == "approval.requested"
    assert payload["approval_id"] == "app-42"
    assert payload["risk_level"] == "HIGH"
    assert payload["prompt_summary"] == "Overwrite configuration file /app/data/prod.yaml"
    assert payload["binding"]["tool_id"] == "filesystem_tool"
    assert payload["binding"]["resource_scope"] == "/app/data"
    assert "file.write" in payload["binding"]["capabilities"]
    assert "decision" not in payload

    # Format with resolution decision
    decision = HumanApprovalDecision(
        approval_id="app-42",
        status=ApprovalStatus.APPROVED,
        actor="devops-lead@company.com",
        reason="Approved after code review",
    )
    res_payload = _format_generic_payload(req, event_type="approval.resolved", decision=decision)
    assert res_payload["event_type"] == "approval.resolved"
    assert res_payload["decision"]["status"] == "APPROVED"
    assert res_payload["decision"]["actor"] == "devops-lead@company.com"


def test_slack_payload_format() -> None:
    """Test Slack Block Kit payload structure."""
    req = _make_sample_request(RiskLevel.CRITICAL)
    slack_payload = _format_slack_payload(req, event_type="approval.requested")

    assert "text" in slack_payload
    assert "blocks" in slack_payload
    blocks = slack_payload["blocks"]
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "header"
    assert "Safety Approval Required" in blocks[0]["text"]["text"]

    # Resolution format
    decision = HumanApprovalDecision(
        approval_id="app-42",
        status=ApprovalStatus.DENIED,
        actor="security@company.com",
        reason="Blocked by compliance policy",
    )
    res_payload = _format_slack_payload(req, event_type="approval.resolved", decision=decision)
    assert "Resolved: [DENIED]" in res_payload["blocks"][0]["text"]["text"]


def test_discord_payload_format() -> None:
    """Test Discord Embed payload structure and color mapping."""
    req_critical = _make_sample_request(RiskLevel.CRITICAL)
    discord_payload = _format_discord_payload(req_critical, event_type="approval.requested")

    assert "embeds" in discord_payload
    embed = discord_payload["embeds"][0]
    assert embed["color"] == 0xE74C3C  # Red for Critical
    assert any(f["name"] == "Approval ID" for f in embed["fields"])

    # High -> Orange
    req_high = _make_sample_request(RiskLevel.HIGH)
    embed_high = _format_discord_payload(req_high, event_type="approval.requested")["embeds"][0]
    assert embed_high["color"] == 0xE67E22

    # Resolution approved -> Green (0x2ECC71)
    decision = HumanApprovalDecision(
        approval_id="app-42",
        status=ApprovalStatus.APPROVED,
        actor="admin@corp.com",
        reason="Approved",
    )
    res_embed = _format_discord_payload(
        req_critical, event_type="approval.resolved", decision=decision
    )["embeds"][0]
    assert res_embed["color"] == 0x2ECC71


def test_hmac_signature_generation_and_verification() -> None:
    """Test HMAC-SHA256 signature computation and tamper verification."""
    payload_bytes = b'{"approval_id": "app-100", "status": "PENDING"}'
    signing_key = "secure-nexus-webhook-key"

    signature = compute_hmac_signature(payload_bytes, signing_key)
    assert isinstance(signature, str)
    assert len(signature) == 64  # SHA-256 hex is 64 characters

    # Verification with sha256= prefix
    assert verify_hmac_signature(payload_bytes, f"sha256={signature}", signing_key) is True
    # Verification without prefix
    assert verify_hmac_signature(payload_bytes, signature, signing_key) is True

    # Tampered payload fails
    tampered_bytes = b'{"approval_id": "app-100", "status": "APPROVED"}'
    assert verify_hmac_signature(tampered_bytes, f"sha256={signature}", signing_key) is False

    # Tampered key fails
    assert verify_hmac_signature(payload_bytes, f"sha256={signature}", "wrong-key") is False

    # Empty inputs fail
    assert verify_hmac_signature(payload_bytes, "", signing_key) is False
    assert verify_hmac_signature(payload_bytes, signature, "") is False


def test_url_format_auto_detection() -> None:
    """Test automatic provider format inference from webhook destination URL."""
    slack_url = "https://hooks.slack.com/mock-testing-endpoint"
    discord_url = "https://discord.com/api/webhooks/mock-testing-endpoint"
    discordapp_url = "https://discordapp.com/api/webhooks/mock-testing-endpoint"
    custom_url = "https://ops-gateway.internal.corp/api/v1/approvals"

    assert (
        WebhookApprovalNotifier._resolve_format(slack_url, WebhookFormat.AUTO)
        == WebhookFormat.SLACK
    )
    assert (
        WebhookApprovalNotifier._resolve_format(discord_url, WebhookFormat.AUTO)
        == WebhookFormat.DISCORD
    )
    assert (
        WebhookApprovalNotifier._resolve_format(discordapp_url, WebhookFormat.AUTO)
        == WebhookFormat.DISCORD
    )
    assert (
        WebhookApprovalNotifier._resolve_format(custom_url, WebhookFormat.AUTO)
        == WebhookFormat.GENERIC
    )

    # Explicit format overrides auto-detection
    assert (
        WebhookApprovalNotifier._resolve_format(slack_url, WebhookFormat.GENERIC)
        == WebhookFormat.GENERIC
    )


@pytest.mark.asyncio
async def test_webhook_notifier_dispatch_success_with_hmac() -> None:
    """Test successful webhook dispatch with HMAC header and payload delivery."""
    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        notifier = WebhookApprovalNotifier(
            webhook_url="https://api.internal/webhook",
            format=WebhookFormat.GENERIC,
            signing_key="super-secret-key",
            http_client=client,
        )

        req = _make_sample_request()
        ok = await notifier.notify_approval_required(req)
        assert ok is True
        assert len(captured_requests) == 1

        sent_req = captured_requests[0]
        assert sent_req.headers["Content-Type"] == "application/json"
        assert "X-NexusAI-Signature" in sent_req.headers
        sig_header = sent_req.headers["X-NexusAI-Signature"]
        assert sig_header.startswith("sha256=")

        # Verify signature on receiver side
        body_bytes = sent_req.read()
        assert verify_hmac_signature(body_bytes, sig_header, "super-secret-key") is True

        payload_obj = json.loads(body_bytes.decode("utf-8"))
        assert payload_obj["event_type"] == "approval.requested"
        assert payload_obj["approval_id"] == "app-42"

        # Now test resolution
        decision = HumanApprovalDecision(
            approval_id="app-42",
            status=ApprovalStatus.APPROVED,
            actor="operator@nexus.ai",
            reason="Approved by SRE on-call",
        )
        ok_res = await notifier.notify_approval_resolved(req, decision)
        assert ok_res is True
        assert len(captured_requests) == 2
        res_obj = json.loads(captured_requests[1].read().decode("utf-8"))
        assert res_obj["event_type"] == "approval.resolved"
        assert res_obj["decision"]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_webhook_notifier_client_error_no_retry() -> None:
    """Test that HTTP 4xx client errors are not retried."""
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, text="Bad Request")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        notifier = WebhookApprovalNotifier(
            webhook_url="https://api.internal/webhook",
            max_retries=3,
            http_client=client,
        )
        req = _make_sample_request()
        ok = await notifier.notify_approval_required(req)
        assert ok is False
        assert attempts == 1  # 4xx client errors abort immediately without retries


@pytest.mark.asyncio
async def test_webhook_notifier_server_error_retry_recovery() -> None:
    """Test that HTTP 5xx server errors retry and succeed when service recovers."""
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        notifier = WebhookApprovalNotifier(
            webhook_url="https://api.internal/webhook",
            max_retries=3,
            retry_backoff_seconds=0.01,
            http_client=client,
        )
        req = _make_sample_request()
        ok = await notifier.notify_approval_required(req)
        assert ok is True
        assert attempts == 3


@pytest.mark.asyncio
async def test_webhook_notifier_network_failure_isolation() -> None:
    """Test that network exceptions are safely caught and return False without raising."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Network unreachable")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        notifier = WebhookApprovalNotifier(
            webhook_url="https://api.internal/webhook",
            max_retries=1,
            retry_backoff_seconds=0.01,
            http_client=client,
        )
        req = _make_sample_request()
        ok = await notifier.notify_approval_required(req)
        assert ok is False
