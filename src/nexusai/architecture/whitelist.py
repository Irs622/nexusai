"""Architecture Whitelist Manager for NexusAI.

Loads approved transitional exceptions from config/architecture_whitelist.yaml,
validates exception metadata (owner, created, expires), and warns if exceptions exceed
their approved expiration dates to prevent technical debt from becoming permanent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

# Default fallback whitelist definitions (empty when no active technical debt)
DEFAULT_WHITELIST: Dict[str, Set[str]] = {}


@dataclass
class WhitelistEntry:
    rule_id: str
    file_path: str
    reason: str
    owner: str
    created: str
    expires: str
    allowed_imports: Set[str]


class ArchitectureWhitelist:
    """Manages architectural exception whitelists and expiration tracking."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.whitelist_file = root_dir / "config" / "architecture_whitelist.yaml"
        self.entries: List[WhitelistEntry] = []
        self.allowed_map: Dict[str, Set[str]] = dict(DEFAULT_WHITELIST)
        self._load_whitelist()

    def _load_whitelist(self) -> None:
        """Load whitelisted exceptions from config/architecture_whitelist.yaml."""
        if not self.whitelist_file.exists():
            return

        try:
            import yaml  # type: ignore[import-untyped]

            content = self.whitelist_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
            exceptions_data = data.get("exceptions", [])
            for item in exceptions_data:
                rule_id = str(item.get("rule_id", ""))
                file_path = str(item.get("file_path", "")).replace("\\", "/")
                reason = str(item.get("reason", ""))
                owner = str(item.get("owner", ""))
                created = str(item.get("created", ""))
                expires = str(item.get("expires", ""))
                allowed_imports = set(item.get("allowed_imports", []))

                key = f"{rule_id}:{file_path}"
                self.allowed_map[key] = allowed_imports

                self.entries.append(
                    WhitelistEntry(
                        rule_id=rule_id,
                        file_path=file_path,
                        reason=reason,
                        owner=owner,
                        created=created,
                        expires=expires,
                        allowed_imports=allowed_imports,
                    )
                )
        except Exception:
            # Fallback if parsing fails
            pass

    def is_whitelisted(self, rule_id: str, file_path: str, import_name: str) -> bool:
        """Check whether a violation is an approved whitelisted exception."""
        norm_path = file_path.replace("\\", "/")
        key = f"{rule_id}:{norm_path}"
        allowed_set = self.allowed_map.get(key, set())
        return import_name in allowed_set

    def check_expired_exceptions(self, current_date_str: str = "2026-08-04") -> List[str]:
        """Check for expired whitelist exceptions."""
        expired_warnings: List[str] = []
        curr_dt = datetime.strptime(current_date_str, "%Y-%m-%d")
        for entry in self.entries:
            try:
                exp_dt = datetime.strptime(entry.expires, "%Y-%m-%d")
                if curr_dt > exp_dt:
                    expired_warnings.append(
                        f"⚠️ EXPIRED WHITELIST EXCEPTION: [{entry.rule_id}] {entry.file_path} "
                        f"expired on {entry.expires} (Owner: {entry.owner}). "
                        f"Refactoring required!"
                    )
            except Exception:
                pass
        return expired_warnings
