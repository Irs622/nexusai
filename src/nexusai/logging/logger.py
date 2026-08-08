"""
Structured Logger Manager powered by Loguru.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as logger

from nexusai.core.config import LoggingSettings

__all__ = ["logger", "setup_logger", "log_audit"]


def setup_logger(settings: LoggingSettings) -> None:
    """Configure Loguru sinks for console, system log file, and audit log file."""
    logger.remove()
    logger.enable("nexusai")

    # Console sink
    logger.add(
        sys.stderr,
        level=settings.level,
        format=settings.format,
        colorize=True,
    )

    # File sink for general application logs
    log_file_path = Path(settings.file_path)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_file_path),
        level=settings.level,
        format=settings.format,
        rotation=settings.rotation,
        enqueue=True,
    )

    # File sink for security audit logs
    audit_file_path = Path(settings.audit_log_path)
    audit_file_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(audit_file_path),
        level="INFO",
        filter=lambda record: "audit" in record["extra"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {extra[audit]} | {message}",
        rotation=settings.rotation,
        enqueue=True,
    )


def log_audit(event: str, details: dict[str, str | bool | int]) -> None:
    """Log a security or operational event to the audit trail."""
    audit_logger = logger.bind(audit="AUDIT_EVENT")
    audit_logger.info(f"EVENT: {event} | DETAILS: {details}")
