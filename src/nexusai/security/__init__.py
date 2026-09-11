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
    "Identity",
    "Role",
    "TenantContext",
    "ApiKeyRecord",
    "ApiKeyService",
    "AuthMiddleware",
    "RbacEngine",
    "Capability",
    "CapabilityProfile",
    "CapabilityResolver",
    "TrustLevel",
    "ContextContent",
    "classify_trust_level",
    "sanitize_tool_output",
    "format_content_with_boundary",
    "tag_context_content",
    "OutputValidator",
    "ValidationResult",
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
    if name in ("Identity", "Role", "TenantContext"):
        import nexusai.security.identity as _identity

        return getattr(_identity, name)
    if name in ("ApiKeyRecord", "ApiKeyService", "AuthMiddleware"):
        import nexusai.security.authentication as _auth

        return getattr(_auth, name)
    if name == "RbacEngine":
        from nexusai.security.authorization import RbacEngine

        return RbacEngine
    if name in ("Capability", "CapabilityProfile", "CapabilityResolver"):
        import nexusai.security.capability as _capability

        return getattr(_capability, name)
    if name in (
        "TrustLevel",
        "ContextContent",
        "classify_trust_level",
        "sanitize_tool_output",
        "format_content_with_boundary",
        "tag_context_content",
    ):
        import nexusai.security.trust_boundary as _trust

        return getattr(_trust, name)
    if name in ("OutputValidator", "ValidationResult"):
        import nexusai.security.output_validator as _validator

        return getattr(_validator, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
