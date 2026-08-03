"""
Security Package.
"""

from typing import Any

__all__ = ["SecurityGuard", "RiskLevel", "ActionRequest", "InputSanitizer"]


def __getattr__(name: str) -> Any:
    if name in ("SecurityGuard", "RiskLevel", "ActionRequest"):
        import nexusai.security.guard as _guard
        return getattr(_guard, name)
    if name == "InputSanitizer":
        from nexusai.security.sanitizer import InputSanitizer
        return InputSanitizer
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
