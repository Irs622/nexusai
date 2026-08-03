"""
Input Sanitizer & Path Validator.
"""

from __future__ import annotations

from pathlib import Path
from nexusai.core.errors import SecurityError


class InputSanitizer:
    """Sanitizes terminal command inputs and file paths against security policies."""

    def __init__(self, forbidden_commands: list[str], protected_paths: list[str]) -> None:
        self.forbidden_commands = forbidden_commands
        self.protected_paths = [Path(p).resolve() for p in protected_paths]

    def validate_command(self, command: str) -> None:
        """Check command string against forbidden pattern blacklist."""
        cmd_normalized = command.strip().lower()

        for forbidden in self.forbidden_commands:
            if forbidden.lower() in cmd_normalized:
                raise SecurityError(
                    f"Command execution blocked: Contains forbidden pattern '{forbidden}'",
                    details={"command": command, "forbidden_pattern": forbidden},
                )

    def validate_path(self, target_path: str | Path, allow_create: bool = False) -> Path:
        """Validate path target against protected system directories."""
        resolved = Path(target_path).expanduser().resolve()

        for protected in self.protected_paths:
            if resolved == protected or protected in resolved.parents:
                raise SecurityError(
                    f"Access blocked: Path '{resolved}' resides within protected system directory '{protected}'",
                    details={"target_path": str(resolved), "protected_directory": str(protected)},
                )

        return resolved
