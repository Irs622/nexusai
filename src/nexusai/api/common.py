"""Shared helpers for the NexusAI API package."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import HTTPException

from nexusai.logging.logger import logger


def resolve_web_dir() -> Path:
    """Locate the static web UI directory.

    Resolution order: ``NEXUSAI_WEB_DIR`` env var, the source checkout layout
    (``<repo>/web``), then ``./web`` relative to the working directory (used by
    non-editable installs such as the production container).
    """
    env_dir = os.getenv("NEXUSAI_WEB_DIR")
    if env_dir:
        return Path(env_dir)
    checkout_dir = Path(__file__).resolve().parent.parent.parent.parent / "web"
    if checkout_dir.exists():
        return checkout_dir
    return Path.cwd() / "web"


web_dir = resolve_web_dir()


def internal_error(endpoint: str, exc: Exception) -> HTTPException:
    """Log an unexpected failure and build a sanitized HTTP 500 response.

    The exception detail and stack trace go only to the server log; clients get
    an opaque reference ID that operators can correlate with the log entry.
    """
    ref_id = uuid.uuid4().hex[:8]
    logger.opt(exception=exc).error("Internal error in {} [ref:{}]", endpoint, ref_id)
    return HTTPException(status_code=500, detail=f"Internal server error (reference: {ref_id})")


# Backward-compatible private alias.
_internal_error = internal_error
