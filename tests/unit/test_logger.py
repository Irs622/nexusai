"""
Unit tests for Logger and Audit Logger.
"""

from pathlib import Path

from loguru import logger

from nexusai.core.config import LoggingSettings
from nexusai.logging.logger import log_audit, setup_logger


def test_setup_logger_and_audit(tmp_path: Path) -> None:
    app_log = tmp_path / "app.log"
    audit_log = tmp_path / "audit.log"

    settings = LoggingSettings(
        level="DEBUG",
        format="{message}",
        file_path=str(app_log),
        audit_log_path=str(audit_log),
        rotation="1 MB",
    )

    setup_logger(settings)
    log_audit("TEST_EVENT", {"detail": "unit_test"})
    logger.complete()
    logger.remove()

    assert audit_log.exists()
    content = audit_log.read_text(encoding="utf-8")
    assert "TEST_EVENT" in content
    assert "unit_test" in content
