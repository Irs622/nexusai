"""
SecurityGuard and Risk Level Evaluator.
"""

from enum import Enum
from pydantic import BaseModel
from nexusai.core.config import SecuritySettings
from nexusai.core.errors import SecurityError
from nexusai.logging.logger import log_audit
from nexusai.security.sanitizer import InputSanitizer


class RiskLevel(str, Enum):
    LOW = "LOW"            # Read-only information checks
    MEDIUM = "MEDIUM"      # Non-destructive side effects (open app, speak)
    HIGH = "HIGH"          # Potentially modifying actions (file edit, terminal execution)
    CRITICAL = "CRITICAL"  # Destructive actions (delete file, system settings edit)


class ActionRequest(BaseModel):
    action_name: str
    risk_level: RiskLevel
    description: str
    parameters: dict[str, str]


class SecurityGuard:
    """Evaluates security permissions, sanitizes inputs, and logs audit trails."""

    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings
        self.sanitizer = InputSanitizer(
            forbidden_commands=settings.forbidden_commands,
            protected_paths=settings.protected_paths,
        )

    def evaluate_permission(self, request: ActionRequest, user_confirmed: bool = False) -> bool:
        """Determine if an action is permitted, requires prompt confirmation, or is denied."""
        # Sanitize command if present
        if "command" in request.parameters:
            self.sanitizer.validate_command(request.parameters["command"])

        # Sanitize path if present
        if "path" in request.parameters:
            self.sanitizer.validate_path(request.parameters["path"])

        # Check risk level policies
        if request.risk_level == RiskLevel.LOW:
            log_audit("ACTION_PERMITTED", {"action": request.action_name, "risk": "LOW"})
            return True

        if request.risk_level == RiskLevel.MEDIUM:
            if self.settings.auto_approve_low_risk or user_confirmed:
                log_audit("ACTION_PERMITTED", {"action": request.action_name, "risk": "MEDIUM"})
                return True
            return False

        if request.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if user_confirmed or not self.settings.strict_mode:
                log_audit("ACTION_PERMITTED_BY_USER", {"action": request.action_name, "risk": request.risk_level.value})
                return True
            log_audit("ACTION_REQUIRES_CONFIRMATION", {"action": request.action_name, "risk": request.risk_level.value})
            return False

        return False
