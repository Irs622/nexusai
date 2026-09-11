"""API Key Authentication Service and Starlette Middleware for NexusAI."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from nexusai.core.errors import AuthenticationError, RateLimitExceededError
from nexusai.security.identity import Identity, Role, TenantContext


@dataclass
class ApiKeyRecord:
    """Secure metadata record representing a registered API key.

    In accordance with security invariants, only the canonical SHA-256 hash of the
    key is ever persisted or kept in memory.
    """

    key_hash: str
    tenant_id: str
    user_id: str
    role: Role
    name: str = ""
    key_id: str = ""
    is_active: bool = True
    rate_limit_per_minute: int = 100
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    @property
    def is_revoked(self) -> bool:
        """Check if API key has been revoked."""
        return not self.is_active


class ApiKeyService:
    """Issues, hashes, stores, authenticates, and enforces rate limits on API keys."""

    KEY_PREFIX = "nx_live_"

    def __init__(
        self,
        storage_path: str | Path | None = None,
        default_rate_limit: int = 100,
        rate_limit_per_minute: int | None = None,
    ) -> None:
        """Initialize ApiKeyService with optional persistence path and rate limit."""
        self.storage_path = Path(storage_path) if storage_path else None
        self.default_rate_limit = (
            rate_limit_per_minute if rate_limit_per_minute is not None else default_rate_limit
        )
        self._records: dict[str, ApiKeyRecord] = {}
        self._rate_limiter: dict[str, list[float]] = {}
        self._lock = threading.Lock()

        if self.storage_path and self.storage_path.is_file():
            self.load_keys()

    @property
    def _keys(self) -> dict[str, ApiKeyRecord]:
        """Internal records alias for inspection and backward compatibility."""
        return self._records

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """Compute canonical SHA-256 hex digest of raw API key."""
        return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

    def generate_key(
        self,
        tenant_id: str,
        user_id: str,
        role: Role,
        name: str = "",
        rate_limit_per_minute: int | None = None,
        expires_at: float | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        """Generate a cryptographically secure random API key, store its SHA-256 hash, and return it.

        Args:
            tenant_id: Tenant or workspace identifier.
            user_id: User or service-account identifier.
            role: Assigned RBAC role.
            name: Optional human-readable description.
            rate_limit_per_minute: Optional custom rate limit.
            expires_at: Optional UTC expiration timestamp.

        Returns:
            Tuple of (raw_api_key_string, ApiKeyRecord).
        """
        raw_token = secrets.token_urlsafe(32)
        raw_key = f"{self.KEY_PREFIX}{raw_token}"
        key_hash = self.hash_key(raw_key)

        record = ApiKeyRecord(
            key_hash=key_hash,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            name=name,
            key_id=key_hash[:16],
            is_active=True,
            rate_limit_per_minute=(
                rate_limit_per_minute
                if rate_limit_per_minute is not None
                else self.default_rate_limit
            ),
            created_at=time.time(),
            expires_at=expires_at,
        )

        with self._lock:
            self._records[key_hash] = record
            if self.storage_path:
                self.save_keys()

        return raw_key, record

    def create_api_key(
        self,
        tenant_id: str,
        user_id: str,
        role: Role,
        name: str = "",
        rate_limit_per_minute: int | None = None,
        expires_in_seconds: float | None = None,
        expires_at: float | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        """Generate and register an API key, supporting expires_in_seconds."""
        if expires_in_seconds is not None and expires_at is None:
            expires_at = time.time() + expires_in_seconds
        return self.generate_key(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            name=name,
            rate_limit_per_minute=rate_limit_per_minute,
            expires_at=expires_at,
        )

    def register_raw_key(
        self,
        raw_key: str,
        tenant_id: str,
        user_id: str,
        role: Role,
        name: str = "",
        rate_limit_per_minute: int | None = None,
        expires_at: float | None = None,
    ) -> ApiKeyRecord:
        """Register a known key string by immediately hashing it and storing the record."""
        key_hash = self.hash_key(raw_key)
        record = ApiKeyRecord(
            key_hash=key_hash,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            name=name,
            key_id=key_hash[:16],
            is_active=True,
            rate_limit_per_minute=(
                rate_limit_per_minute
                if rate_limit_per_minute is not None
                else self.default_rate_limit
            ),
            created_at=time.time(),
            expires_at=expires_at,
        )
        with self._lock:
            self._records[key_hash] = record
            if self.storage_path:
                self.save_keys()
        return record

    def register_record(self, record: ApiKeyRecord) -> None:
        """Register a pre-hashed ApiKeyRecord into storage."""
        if not record.key_id:
            record.key_id = record.key_hash[:16]
        with self._lock:
            self._records[record.key_hash] = record
            if self.storage_path:
                self.save_keys()

    def get_record(self, key_hash: str) -> ApiKeyRecord | None:
        """Retrieve key record by its SHA-256 hash."""
        with self._lock:
            return self._records.get(key_hash)

    def revoke_key(self, key_id_or_hash: str) -> bool:
        """Revoke key access immediately by key_id or SHA-256 hash."""
        with self._lock:
            record = self._records.get(key_id_or_hash)
            if not record:
                for r in self._records.values():
                    if r.key_id == key_id_or_hash:
                        record = r
                        break
            if record:
                record.is_active = False
                if self.storage_path:
                    self.save_keys()
                return True
            return False

    def revoke_by_raw_key(self, raw_key: str) -> bool:
        """Revoke key access immediately by raw key string."""
        return self.revoke_key(self.hash_key(raw_key))

    def check_rate_limit(self, key_id_or_hash: str) -> None:
        """Evaluate sliding-window rate limit for a key_id or key_hash."""
        with self._lock:
            record = self._records.get(key_id_or_hash)
            if not record:
                for r in self._records.values():
                    if r.key_id == key_id_or_hash:
                        record = r
                        break
            if not record:
                return

            key_hash = record.key_hash
            now = time.time()
            timestamps = self._rate_limiter.setdefault(key_hash, [])
            cutoff = now - 60.0
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= record.rate_limit_per_minute:
                self._rate_limiter[key_hash] = valid_timestamps
                raise RateLimitExceededError(
                    f"Rate limit exceeded: max {record.rate_limit_per_minute} requests per minute",
                    details={"rate_limit": str(record.rate_limit_per_minute), "key_hash": key_hash},
                )
            valid_timestamps.append(now)
            self._rate_limiter[key_hash] = valid_timestamps

    def authenticate(self, raw_key: str) -> Identity:
        """Authenticate raw API key, verify active status and expiration, and enforce rate limits.

        Args:
            raw_key: Plaintext API key provided in request.

        Returns:
            Authenticated Identity object.

        Raises:
            AuthenticationError: If key is unknown, revoked, or expired.
            RateLimitExceededError: If key has exceeded sliding-window rate limit.
        """
        if not raw_key or not raw_key.strip():
            raise AuthenticationError("Invalid API key")

        key_hash = self.hash_key(raw_key)

        with self._lock:
            record = self._records.get(key_hash)
            if record is None:
                raise AuthenticationError("Invalid API key", details={"key_hash": key_hash})

            if not record.is_active:
                raise AuthenticationError(
                    "API key has been revoked", details={"key_hash": key_hash}
                )

            now = time.time()
            if record.expires_at is not None and now > record.expires_at:
                raise AuthenticationError("API key has expired", details={"key_hash": key_hash})

            # Sliding-window rate limit enforcement (per minute)
            timestamps = self._rate_limiter.setdefault(key_hash, [])
            cutoff = now - 60.0
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= record.rate_limit_per_minute:
                self._rate_limiter[key_hash] = valid_timestamps
                raise RateLimitExceededError(
                    f"Rate limit exceeded: max {record.rate_limit_per_minute} requests per minute",
                    details={"rate_limit": str(record.rate_limit_per_minute), "key_hash": key_hash},
                )

            valid_timestamps.append(now)
            self._rate_limiter[key_hash] = valid_timestamps

            return Identity(
                tenant_id=record.tenant_id,
                user_id=record.user_id,
                role=record.role,
                api_key_id=record.key_id,
                metadata={"key_name": record.name, "rate_limit": record.rate_limit_per_minute},
            )

    def save_keys(self) -> None:
        """Persist key records to JSON storage path."""
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {h: asdict(r) for h, r in self._records.items()}
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_keys(self) -> None:
        """Load key records from JSON storage path."""
        if not self.storage_path or not self.storage_path.is_file():
            return
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(content)
            for key_hash, r_data in data.items():
                r_data["role"] = Role(r_data["role"])
                self._records[key_hash] = ApiKeyRecord(**r_data)
        except Exception:
            pass


DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/healthz",
        "/readyz",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/",
        "/studio",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware intercepting HTTP requests to enforce API Key authentication."""

    def __init__(
        self,
        app: Any,
        api_key_service: ApiKeyService,
        header_name: str = "X-NexusAI-API-Key",
        exempt_paths: set[str] | frozenset[str] | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.api_key_service = api_key_service
        self.header_name = header_name
        self.exempt_paths = (
            frozenset(exempt_paths) if exempt_paths is not None else DEFAULT_EXEMPT_PATHS
        )
        self.enabled = enabled

    def _is_exempt(self, path: str) -> bool:
        """Determine whether request path is exempt from API key authentication."""
        if path in self.exempt_paths:
            return True
        if path.startswith("/static/"):
            return True
        return False

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Process incoming request through authentication and rate limiting filters."""
        # Allow CORS preflight requests
        if request.method == "OPTIONS":
            return await call_next(request)  # type: ignore[no-any-return]

        if not self.enabled or self._is_exempt(request.url.path):
            return await call_next(request)  # type: ignore[no-any-return]

        raw_key = request.headers.get(self.header_name)
        if not raw_key:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Authentication required: Missing '{self.header_name}' header"},
                headers={"WWW-Authenticate": f"ApiKey header={self.header_name}"},
            )

        try:
            identity = self.api_key_service.authenticate(raw_key)
        except RateLimitExceededError as rle:
            return JSONResponse(
                status_code=429,
                content={"detail": rle.message, "details": rle.details},
                headers={"Retry-After": "60"},
            )
        except AuthenticationError as ae:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Authentication failed: {ae.message}"},
                headers={"WWW-Authenticate": f"ApiKey header={self.header_name}"},
            )

        request.state.identity = identity
        token = TenantContext.set_current_identity(identity)
        try:
            response = await call_next(request)
            return response  # type: ignore[no-any-return]
        finally:
            TenantContext.reset_current_identity(token)
