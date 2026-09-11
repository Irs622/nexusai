"""
Security Package.
"""

from typing import Any

__all__ = [
    "SecurityGuard",
    "RiskLevel",
    "ActionRequest",
    "InputSanitizer",
    "ApprovalTokenService",
]


def __getattr__(name: str) -> Any:
    if name in ("SecurityGuard", "RiskLevel", "ActionRequest"):
        import nexusai.security.guard as _guard

        return getattr(_guard, name)
    if name == "InputSanitizer":
        from nexusai.security.sanitizer import InputSanitizer

        return InputSanitizer
    if name == "ApprovalTokenService":
        from nexusai.security.approval_token import ApprovalTokenService

        return ApprovalTokenService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
