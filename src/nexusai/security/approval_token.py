"""Server-Side Approval Token Service for High/Critical Risk Tool Execution."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any

from nexusai.core.errors import SecurityError
from nexusai.security.identity import TenantContext
from nexusai.security.nonce_store import IDistributedNonceStore, create_distributed_nonce_store


class ApprovalTokenService:
    """Issues, validates, and atomically consumes cryptographic HMAC-SHA256 approval tokens.

    Approval tokens bind a specific tool execution request (tool name, canonical arguments,
    identity, and execution context) with a cryptographic signature, short TTL, and single-use
    replay protection.
    """

    TOKEN_PREFIX = "nexus_appr_"

    def __init__(
        self,
        secret: str | bytes | None = None,
        default_ttl_seconds: float = 300.0,
        nonce_store: IDistributedNonceStore | None = None,
    ) -> None:
        """Initialize ApprovalTokenService with HMAC secret and default expiration window.

        Args:
            secret: Optional HMAC signing secret string or bytes. If omitted, reads from
                NEXUSAI_APPROVAL_SECRET environment variable or generates an in-memory random secret.
            default_ttl_seconds: Token validity window in seconds (default: 300.0s = 5 minutes).
            nonce_store: Optional distributed nonce store instance for single-use replay protection.
        """
        is_production = os.getenv("NEXUSAI_ENV") in ("production", "prod")
        if secret is None:
            env_secret = os.getenv("NEXUSAI_APPROVAL_SECRET")
            if env_secret:
                self._secret_bytes = env_secret.encode("utf-8")
            else:
                if is_production:
                    raise SecurityError(
                        "Production startup aborted: NEXUSAI_APPROVAL_SECRET environment variable must be set for approval token service."
                    )
                self._secret_bytes = secrets.token_bytes(32)
        elif isinstance(secret, str):
            self._secret_bytes = secret.encode("utf-8")
        else:
            self._secret_bytes = secret

        self.default_ttl_seconds = default_ttl_seconds
        self.nonce_store = nonce_store or create_distributed_nonce_store()
        self._consumed_nonces: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def compute_arguments_digest(arguments: dict[str, Any]) -> str:
        """Compute deterministic SHA-256 digest of tool arguments dict."""
        try:
            canonical_json = json.dumps(
                arguments,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except Exception:
            canonical_json = str(sorted(arguments.items()))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _build_signing_payload(
        self,
        user_id: str,
        tool_name: str,
        args_digest: str,
        execution_id: str,
        expires_at_int: int,
        nonce: str,
    ) -> bytes:
        """Build canonical signing payload string bytes."""
        payload_str = f"{user_id}:{tool_name}:{args_digest}:{execution_id}:{expires_at_int}:{nonce}"
        return payload_str.encode("utf-8")

    def _sign_payload(self, payload: bytes) -> str:
        """Generate HMAC-SHA256 hex digest for payload."""
        return hmac.new(self._secret_bytes, payload, hashlib.sha256).hexdigest()

    def create_token(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: str = "anonymous",
        execution_id: str = "",
        ttl_seconds: float | None = None,
    ) -> tuple[str, float]:
        """Issue a new single-use approval token bound to tool, arguments, and identity.

        Args:
            tool_name: Name of tool to authorize.
            arguments: Tool execution parameter dictionary.
            user_id: Caller identity (default: 'anonymous').
            execution_id: Optional execution or session ID.
            ttl_seconds: Optional custom TTL in seconds.

        Returns:
            Tuple of (approval_token_string, expires_at_timestamp).
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = time.time()
        expires_at = now + ttl
        expires_at_int = int(expires_at)
        if user_id in ("anonymous", "", None):
            ambient = TenantContext.get_current_identity()
            if ambient is not None:
                user_id = ambient.user_id

        nonce = secrets.token_hex(16)
        args_digest = self.compute_arguments_digest(arguments)
        payload = self._build_signing_payload(
            user_id=user_id,
            tool_name=tool_name,
            args_digest=args_digest,
            execution_id=execution_id,
            expires_at_int=expires_at_int,
            nonce=nonce,
        )
        signature = self._sign_payload(payload)
        token = f"{self.TOKEN_PREFIX}{nonce}.{expires_at_int}.{signature}"
        return token, float(expires_at_int)

    def parse_token(self, token: str) -> tuple[str, int, str]:
        """Parse token components: (nonce, expires_at_int, signature).

        Raises:
            SecurityError: If token structure or format is invalid.
        """
        if not token or not token.startswith(self.TOKEN_PREFIX):
            raise SecurityError(
                "Invalid approval token format: Missing expected prefix",
                details={"token": token},
            )

        raw = token[len(self.TOKEN_PREFIX) :]
        parts = raw.split(".")
        if len(parts) != 3:
            raise SecurityError(
                "Invalid approval token structure: Expected 3 segments",
                details={"token": token},
            )

        nonce, exp_str, signature = parts
        try:
            expires_at_int = int(exp_str)
        except ValueError as err:
            raise SecurityError(
                "Invalid approval token expiration timestamp",
                details={"token": token, "error": str(err)},
            ) from err

        return nonce, expires_at_int, signature

    def validate_and_consume(
        self,
        token: str,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: str = "anonymous",
        execution_id: str = "",
    ) -> bool:
        """Validate signature, binding, and freshness, then atomically mark token consumed.

        Args:
            token: The approval token string to validate.
            tool_name: The tool attempting execution.
            arguments: The execution arguments.
            user_id: Identity attempting execution.
            execution_id: Execution context ID.

        Returns:
            True if authorization is granted.

        Raises:
            SecurityError: If token is expired, replayed, tampered, or mismatched.
        """
        nonce, expires_at_int, signature = self.parse_token(token)
        now = time.time()
        # 1. Expiration check
        if now > expires_at_int:
            raise SecurityError(
                f"Approval token expired at {expires_at_int} (current time: {int(now)})",
                details={
                    "token": token,
                    "expires_at": str(expires_at_int),
                    "current_time": str(int(now)),
                    "tool_name": tool_name,
                },
            )

        # 2. Signature & Binding verification
        if user_id in ("anonymous", "", None):
            ambient = TenantContext.get_current_identity()
            if ambient is not None:
                user_id = ambient.user_id

        args_digest = self.compute_arguments_digest(arguments)
        expected_payload = self._build_signing_payload(
            user_id=user_id,
            tool_name=tool_name,
            args_digest=args_digest,
            execution_id=execution_id,
            expires_at_int=expires_at_int,
            nonce=nonce,
        )
        expected_signature = self._sign_payload(expected_payload)

        if not hmac.compare_digest(expected_signature, signature):
            raise SecurityError(
                f"Approval token binding mismatch or invalid signature for tool '{tool_name}'",
                details={
                    "token": token,
                    "tool_name": tool_name,
                    "expected_args_digest": args_digest,
                },
            )

        # 3. Distributed atomic single-use consumption & replay check
        ttl_remaining = max(float(expires_at_int - now), 1.0)
        with self._lock:
            if (
                not self.nonce_store.consume_nonce(nonce, ttl_remaining)
                or nonce in self._consumed_nonces
            ):
                raise SecurityError(
                    f"Approval token has already been consumed (replay detected for nonce '{nonce}')",
                    details={"token": token, "nonce": nonce, "tool_name": tool_name},
                )
            self._consumed_nonces.add(nonce)

        return True
