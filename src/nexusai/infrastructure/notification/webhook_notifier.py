"""Webhook notification gateway implementation for Human-In-The-Loop safety approvals."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from enum import Enum
from typing import Any

import httpx

from nexusai.brain.domain.human_approval import (
    HumanApprovalDecision,
    HumanApprovalRequest,
    RiskLevel,
)
from nexusai.brain.ports.governance_port import IApprovalNotifierPort
from nexusai.logging.logger import logger


class WebhookFormat(str, Enum):
    """Payload serialization formats for outbound notification webhooks."""

    GENERIC = "generic"
    SLACK = "slack"
    DISCORD = "discord"
    AUTO = "auto"


def compute_hmac_signature(payload_bytes: bytes, signing_key: str) -> str:
    """Compute HMAC-SHA256 hex digest for webhook payload bytes.

    Args:
        payload_bytes: Raw serialized request body bytes.
        signing_key: Shared secret key for signature calculation.

    Returns:
        Hexadecimal SHA-256 HMAC digest string.
    """
    return hmac.new(signing_key.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def verify_hmac_signature(payload_bytes: bytes, signature_header: str, signing_key: str) -> bool:
    """Verify an incoming HMAC-SHA256 signature header against payload bytes.

    Supports headers with or without the 'sha256=' prefix.

    Args:
        payload_bytes: Raw received request body bytes.
        signature_header: Header value (e.g. 'sha256=abcdef...' or 'abcdef...').
        signing_key: Shared secret key.

    Returns:
        True if signature is valid and authentic, False otherwise.
    """
    if not signature_header or not signing_key:
        return False

    raw_signature = signature_header.strip()
    if raw_signature.lower().startswith("sha256="):
        raw_signature = raw_signature[7:].strip()

    expected_signature = compute_hmac_signature(payload_bytes, signing_key)
    return hmac.compare_digest(expected_signature.lower(), raw_signature.lower())


def _format_generic_payload(
    request: HumanApprovalRequest,
    event_type: str,
    decision: HumanApprovalDecision | None = None,
) -> dict[str, Any]:
    """Build a vendor-neutral canonical JSON webhook payload."""
    payload: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": time.time(),
        "approval_id": request.approval_id,
        "status": request.status.value,
        "risk_level": request.risk_level.value,
        "prompt_summary": request.prompt_summary,
        "binding": {
            "session_id": request.binding.session_id,
            "execution_id": request.binding.execution_id,
            "plan_fingerprint": request.binding.plan_fingerprint,
            "node_id": request.binding.node_id,
            "tool_id": request.binding.tool_id,
            "tool_version": request.binding.tool_version,
            "resource_scope": request.binding.resource_scope,
            "capabilities": sorted([c.value for c in request.binding.requested_capabilities]),
            "action_digest": request.binding.action_digest,
        },
        "created_at": request.created_at,
        "expires_at": request.expires_at,
        "metadata": dict(request.metadata),
    }
    if decision is not None:
        payload["decision"] = {
            "status": decision.status.value,
            "actor": decision.actor,
            "reason": decision.reason,
            "decision_timestamp": decision.decision_timestamp,
        }
    return payload


def _format_slack_payload(
    request: HumanApprovalRequest,
    event_type: str,
    decision: HumanApprovalDecision | None = None,
) -> dict[str, Any]:
    """Format an outbound payload conforming to Slack Incoming Webhook Block Kit specification."""
    is_resolution = decision is not None
    if is_resolution:
        status_label = decision.status.value if decision else "RESOLVED"
        title = f"✅ Safety Approval Resolved: [{status_label}]"
        badge = f"*{decision.status.value}* by `{decision.actor}`" if decision else ""
    else:
        title = "🚨 Safety Approval Required"
        badge = f"`{request.risk_level.value}`"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": title,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Risk Level:*\n{badge}"},
                {"type": "mrkdwn", "text": f"*Tool ID:*\n`{request.binding.tool_id}`"},
                {"type": "mrkdwn", "text": f"*Execution ID:*\n`{request.binding.execution_id}`"},
                {"type": "mrkdwn", "text": f"*Approval ID:*\n`{request.approval_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary:*\n{request.prompt_summary}",
            },
        },
    ]

    if is_resolution and decision:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Resolution Reason:*\n{decision.reason}",
                },
            }
        )

    return {
        "text": f"{title} - {request.binding.tool_id} ({request.approval_id})",
        "blocks": blocks,
    }


def _format_discord_payload(
    request: HumanApprovalRequest,
    event_type: str,
    decision: HumanApprovalDecision | None = None,
) -> dict[str, Any]:
    """Format an outbound payload conforming to Discord Webhook Embed specification."""
    is_resolution = decision is not None
    # Color coding: Red for Critical/High/Denied, Green for Approved, Orange for Medium, Blue for Low
    if is_resolution and decision:
        color = 0x2ECC71 if decision.status.value == "APPROVED" else 0xE74C3C
        title = f"Safety Approval Resolved: {decision.status.value}"
    else:
        color_map = {
            RiskLevel.CRITICAL: 0xE74C3C,  # Red
            RiskLevel.HIGH: 0xE67E22,  # Orange
            RiskLevel.MEDIUM: 0xF1C40F,  # Yellow
            RiskLevel.LOW: 0x3498DB,  # Blue
        }
        color = color_map.get(request.risk_level, 0xE74C3C)
        title = "🚨 Human Safety Approval Required"

    fields: list[dict[str, Any]] = [
        {"name": "Approval ID", "value": f"`{request.approval_id}`", "inline": True},
        {"name": "Risk Level", "value": f"`{request.risk_level.value}`", "inline": True},
        {"name": "Tool ID", "value": f"`{request.binding.tool_id}`", "inline": True},
        {"name": "Execution ID", "value": f"`{request.binding.execution_id}`", "inline": True},
        {
            "name": "Action Digest",
            "value": f"`{request.binding.action_digest[:16]}...`",
            "inline": False,
        },
    ]

    if is_resolution and decision:
        fields.append({"name": "Decision By", "value": decision.actor, "inline": True})
        fields.append({"name": "Reason", "value": decision.reason, "inline": False})

    embed = {
        "title": title,
        "description": request.prompt_summary,
        "color": color,
        "fields": fields,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(request.created_at)),
    }

    return {
        "content": f"{title} — `{request.binding.tool_id}`",
        "embeds": [embed],
    }


class WebhookApprovalNotifier(IApprovalNotifierPort):
    """Outbound HTTP Webhook notification gateway for Human Safety Approval requests."""

    def __init__(
        self,
        webhook_url: str,
        format: WebhookFormat | str = WebhookFormat.AUTO,
        signing_key: str | None = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        http_client: httpx.AsyncClient | None = None,
        custom_headers: Mapping[str, str] | None = None,
    ) -> None:
        """Initialize the WebhookApprovalNotifier.

        Args:
            webhook_url: Target destination HTTP/HTTPS endpoint.
            format: WebhookFormat enum or string (generic, slack, discord, auto).
            signing_key: Optional HMAC-SHA256 secret key for X-NexusAI-Signature header.
            timeout_seconds: HTTP client request timeout in seconds.
            max_retries: Maximum number of delivery retry attempts upon transient failure.
            retry_backoff_seconds: Base exponential backoff factor in seconds.
            http_client: Optional pre-configured httpx.AsyncClient instance.
            custom_headers: Optional additional headers to include in dispatch requests.
        """
        self.webhook_url = webhook_url
        self.raw_format = WebhookFormat(format) if isinstance(format, str) else format
        self.signing_key = signing_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._custom_headers = dict(custom_headers or {})
        self._http_client = http_client
        self._owns_client = http_client is None

        # Resolve effective format
        self.format = self._resolve_format(self.webhook_url, self.raw_format)

    @staticmethod
    def _resolve_format(url: str, specified: WebhookFormat) -> WebhookFormat:
        """Infer target platform format from endpoint URL if set to AUTO."""
        if specified != WebhookFormat.AUTO:
            return specified

        lower_url = url.lower()
        if "hooks.slack.com" in lower_url:
            return WebhookFormat.SLACK
        if "discord.com/api/webhooks" in lower_url or "discordapp.com/api/webhooks" in lower_url:
            return WebhookFormat.DISCORD
        return WebhookFormat.GENERIC

    def _format_payload(
        self,
        request: HumanApprovalRequest,
        event_type: str,
        decision: HumanApprovalDecision | None = None,
    ) -> dict[str, Any]:
        """Format request domain object according to target webhook provider schema."""
        if self.format == WebhookFormat.SLACK:
            return _format_slack_payload(request, event_type, decision=decision)
        if self.format == WebhookFormat.DISCORD:
            return _format_discord_payload(request, event_type, decision=decision)
        return _format_generic_payload(request, event_type, decision=decision)

    async def _send_http_request(self, body_bytes: bytes, headers: dict[str, str]) -> bool:
        """Send HTTP POST request with retry backoff and failure isolation."""
        client = self._http_client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
            close_client = True

        try:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        self.webhook_url,
                        content=body_bytes,
                        headers=headers,
                    )
                    if 200 <= response.status_code < 300:
                        return True
                    if 400 <= response.status_code < 500:
                        logger.warning(
                            f"[WebhookApprovalNotifier] Webhook client error ({response.status_code}) "
                            f"at {self.webhook_url}: {response.text[:200]}"
                        )
                        return False

                    logger.warning(
                        f"[WebhookApprovalNotifier] Webhook server error ({response.status_code}) "
                        f"on attempt {attempt + 1}/{self.max_retries + 1}"
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    logger.warning(
                        f"[WebhookApprovalNotifier] Network error on attempt "
                        f"{attempt + 1}/{self.max_retries + 1}: {exc}"
                    )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
            return False
        finally:
            if close_client and client is not None:
                await client.aclose()

    async def notify_approval_required(
        self,
        request: HumanApprovalRequest,
    ) -> bool:
        """Dispatch outbound notification that high-risk action requires human operator approval."""
        try:
            payload_dict = self._format_payload(request, event_type="approval.requested")
            body_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "User-Agent": "NexusAI-Governance/1.0",
                **self._custom_headers,
            }

            if self.signing_key:
                signature = compute_hmac_signature(body_bytes, self.signing_key)
                headers["X-NexusAI-Signature"] = f"sha256={signature}"

            return await self._send_http_request(body_bytes, headers)
        except Exception as exc:
            logger.warning(
                f"[WebhookApprovalNotifier] Unexpected error during notify_approval_required for '{request.approval_id}': {exc}"
            )
            return False

    async def notify_approval_resolved(
        self,
        request: HumanApprovalRequest,
        decision: HumanApprovalDecision,
    ) -> bool:
        """Dispatch outbound notification that an approval request has been resolved (approved or denied)."""
        try:
            payload_dict = self._format_payload(
                request, event_type="approval.resolved", decision=decision
            )
            body_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "User-Agent": "NexusAI-Governance/1.0",
                **self._custom_headers,
            }

            if self.signing_key:
                signature = compute_hmac_signature(body_bytes, self.signing_key)
                headers["X-NexusAI-Signature"] = f"sha256={signature}"

            return await self._send_http_request(body_bytes, headers)
        except Exception as exc:
            logger.warning(
                f"[WebhookApprovalNotifier] Unexpected error during notify_approval_resolved for '{request.approval_id}': {exc}"
            )
            return False
