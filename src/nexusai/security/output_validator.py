"""Post-LLM Tool Call Output Validator and Defensive Execution Policy Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nexusai.logging.logger import logger
from nexusai.security.capability import CapabilityResolver
from nexusai.security.identity import Identity, Role
from nexusai.security.trust_boundary import TrustLevel


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating an LLM-generated tool execution request.

    Attributes:
        is_valid: True if the tool call is authorized and safe to execute.
        violation_type: Specific policy violation identifier if blocked.
        reason: Diagnostic description of why the tool call was approved, flagged, or rejected.
        requires_approval: True if execution requires explicit human-in-the-loop approval.
        policy_triggered: The defensive policy that flagged or blocked the request.
    """

    is_valid: bool
    violation_type: str | None = None
    reason: str | None = None
    requires_approval: bool = False
    policy_triggered: str | None = None


# Patterns indicating sensitive filesystem artifacts prone to exfiltration
SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(?i)\.env(\.[a-z0-9_]+)?"),
    re.compile(r"(?i)\.ssh(/.*)?"),
    re.compile(r"(?i)\.aws(/.*)?"),
    re.compile(r"(?i)id_rsa|id_ed25519|known_hosts"),
    re.compile(r"(?i)credentials(\.json|\.yaml)?"),
    re.compile(r"(?i)secrets?(\.json|\.yaml)?"),
    re.compile(r"(?i)\.gnupg(/.*)?"),
]

# Patterns for network egress tools
NETWORK_EGRESS_TOOLS = {
    "web_fetcher",
    "fetch_url",
    "mcp:web_fetcher",
    "curl",
    "wget",
    "http_request",
    "netcat",
    "nc",
}

# Patterns indicating privilege escalation attempts
PRIVILEGE_ESCALATION_COMMANDS = [
    re.compile(r"(?i)\b(sudo|su|doas|pkexec)\b"),
    re.compile(r"(?i)\bchmod\s+([0-7]*[4-7][0-7]{2}|\+s)\b"),
    re.compile(r"(?i)\bchown\s+root\b"),
    re.compile(r"(?i)\b(visudo|usermod\s+-aG\s+(sudo|wheel|admin))\b"),
]

# Destructive command patterns for intent misalignment detection
DESTRUCTIVE_COMMAND_PATTERNS = [
    re.compile(r"(?i)\brm\s+(-[rfR]{1,3}\s+.*|/|\*)"),
    re.compile(r"(?i)\b(mkfs|dd\s+if=.*of=/dev/|fdisk|parted)\b"),
    re.compile(r"(?i)\b(shutdown|reboot|init\s+0)\b"),
    re.compile(r"(?i)\bdrop\s+(database|table)\b"),
]


class OutputValidator:
    """Validates LLM-proposed tool calls against trust boundaries and defensive policies."""

    def __init__(
        self,
        max_untrusted_influence: int = 3,
        no_tool_from_untrusted: bool = True,
        no_exfiltration: bool = True,
        no_privilege_escalation: bool = True,
        intent_alignment: bool = True,
        capability_resolver: CapabilityResolver | None = None,
    ) -> None:
        self.max_untrusted_influence = max_untrusted_influence
        self.no_tool_from_untrusted = no_tool_from_untrusted
        self.no_exfiltration = no_exfiltration
        self.no_privilege_escalation = no_privilege_escalation
        self.intent_alignment = intent_alignment
        self.capability_resolver = capability_resolver
        self.untrusted_influence_depth: int = 0
        self.observed_sensitive_files: set[str] = set()
        self.observed_untrusted_texts: list[str] = []

    def record_observation(
        self,
        trust_level: TrustLevel,
        source: str,
        content: str,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        """Track content observed by the LLM to maintain causal influence chains."""
        if trust_level == TrustLevel.UNTRUSTED:
            self.untrusted_influence_depth += 1
            self.observed_untrusted_texts.append(content[:2000])
        elif trust_level == TrustLevel.TRUSTED:
            # System instructions reset untrusted influence
            self.untrusted_influence_depth = 0

        # Detect if a sensitive file was inspected
        args = arguments or {}
        path_arg = str(args.get("path") or args.get("file_path") or args.get("command") or "")
        for pat in SENSITIVE_FILE_PATTERNS:
            if pat.search(path_arg) or (
                tool_name and "file" in tool_name and pat.search(content[:500])
            ):
                self.observed_sensitive_files.add(path_arg)

    def validate_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_goal: str,
        identity: Identity | None = None,
    ) -> ValidationResult:
        """Validate an LLM-proposed tool call against all defensive execution policies.

        Policies:
        1. no_privilege_escalation: Prevent commands/roles requesting higher capabilities than identity holds
        2. no_exfiltration: Block sending data from high-trust sources to network egress
        3. no_tool_from_untrusted: Require explicit approval if influenced by untrusted content
        4. max_untrusted_influence: Limit consecutive tool calls from untrusted sources
        5. intent_alignment: Ensure tool and action match original user task goal
        6. capability_authorization: Verify positive capability grant against caller identity (#34)
        """
        tool_lower = tool_name.lower()
        cmd_str = str(arguments.get("command", ""))
        url_str = str(arguments.get("url", ""))
        goal_lower = user_goal.lower()

        # ---------------------------------------------------------------------
        # Policy 1: no_privilege_escalation
        # ---------------------------------------------------------------------
        if self.no_privilege_escalation:
            for pat in PRIVILEGE_ESCALATION_COMMANDS:
                if pat.search(cmd_str):
                    logger.warning(
                        f"[Security Violation] Privilege escalation attempt blocked: '{tool_name}' with '{cmd_str}'"
                    )
                    return ValidationResult(
                        is_valid=False,
                        violation_type="PRIVILEGE_ESCALATION",
                        reason=f"Privilege escalation command '{cmd_str}' is forbidden by defensive policy.",
                        policy_triggered="no_privilege_escalation",
                    )

            if "role" in arguments and str(arguments["role"]).lower() in (
                "admin",
                "system",
                "root",
            ):
                return ValidationResult(
                    is_valid=False,
                    violation_type="PRIVILEGE_ESCALATION",
                    reason="Attempted role escalation to admin/system in tool arguments.",
                    policy_triggered="no_privilege_escalation",
                )

        # ---------------------------------------------------------------------
        # Policy 2: no_exfiltration
        # ---------------------------------------------------------------------
        is_egress_tool = (
            tool_lower in NETWORK_EGRESS_TOOLS
            or "curl" in cmd_str
            or "wget" in cmd_str
            or bool(url_str)
        )
        if self.no_exfiltration and self.observed_sensitive_files and is_egress_tool:
            payload_str = str(arguments)
            has_sensitive_data = any(
                f in payload_str
                or "token" in payload_str.lower()
                or "secret" in payload_str.lower()
                for f in self.observed_sensitive_files
            )
            if has_sensitive_data or self.untrusted_influence_depth > 0:
                logger.critical(
                    f"[Security Violation] Exfiltration blocked: Egress tool '{tool_name}' called after reading sensitive files: {self.observed_sensitive_files}"
                )
                return ValidationResult(
                    is_valid=False,
                    violation_type="EXFILTRATION",
                    reason=f"Exfiltration pattern detected: Network egress to '{url_str or cmd_str}' blocked after inspecting sensitive files: {list(self.observed_sensitive_files)}",
                    policy_triggered="no_exfiltration",
                )

        # ---------------------------------------------------------------------
        # Policy 3: Intent Alignment & Semantic Matching
        # ---------------------------------------------------------------------
        if self.intent_alignment:
            # Rule 3a: If user asked to "read file", agent cannot invoke "web_fetcher" / network egress
            is_local_file_intent = any(
                k in goal_lower
                for k in (
                    "read file",
                    "open file",
                    "view file",
                    "inspect file",
                    "check file",
                    "examine file",
                )
            ) and not any(
                k in goal_lower
                for k in ("url", "http", "website", "web", "fetch", "download", "online")
            )
            if is_local_file_intent and is_egress_tool:
                logger.warning(
                    f"[Security Violation] Tool call '{tool_name}' blocked due to intent misalignment: User requested local file reading without web egress."
                )
                return ValidationResult(
                    is_valid=False,
                    violation_type="INTENT_MISALIGNMENT",
                    reason=f"Tool '{tool_name}' does not match task goal: User requested local file reading without network egress.",
                    policy_triggered="intent_alignment",
                )

            # Rule 3b: If user asked to "fetch URL", or has benign goal, agent cannot invoke destructive commands
            is_benign_goal = any(
                k in goal_lower
                for k in (
                    "what is",
                    "how to",
                    "show",
                    "list",
                    "read",
                    "check",
                    "summarize",
                    "find",
                    "explain",
                    "fetch url",
                    "read url",
                )
            ) and not any(
                k in goal_lower for k in ("delete", "remove", "wipe", "format", "kill", "drop")
            )
            if is_benign_goal:
                for pat in DESTRUCTIVE_COMMAND_PATTERNS:
                    if pat.search(cmd_str):
                        logger.critical(
                            f"[Security Violation] Destructive command '{cmd_str}' blocked due to intent misalignment with user goal: '{user_goal}'"
                        )
                        return ValidationResult(
                            is_valid=False,
                            violation_type="INTENT_MISALIGNMENT",
                            reason=f"Destructive action '{cmd_str}' does not align with original user intent: '{user_goal}'",
                            policy_triggered="intent_alignment",
                        )

        # ---------------------------------------------------------------------
        # Policy 4: no_tool_from_untrusted
        # ---------------------------------------------------------------------
        if self.no_tool_from_untrusted and self.observed_untrusted_texts:
            # If tool arguments reference specific URLs or commands found in untrusted text
            # that were not present in original user goal, require explicit approval
            for untrusted in self.observed_untrusted_texts:
                if url_str and url_str in untrusted and url_str not in user_goal:
                    logger.warning(
                        f"[Security Policy] Tool call '{tool_name}' influenced by untrusted content (URL: {url_str}): requires approval."
                    )
                    return ValidationResult(
                        is_valid=True,
                        requires_approval=True,
                        violation_type="UNTRUSTED_CONTENT_INFLUENCE",
                        reason=f"Tool call '{tool_name}' references URL '{url_str}' found in untrusted content.",
                        policy_triggered="no_tool_from_untrusted",
                    )
                if (
                    cmd_str
                    and len(cmd_str) > 6
                    and cmd_str in untrusted
                    and cmd_str not in user_goal
                ):
                    logger.warning(
                        f"[Security Policy] Tool call '{tool_name}' influenced by untrusted content (cmd: {cmd_str}): requires approval."
                    )
                    return ValidationResult(
                        is_valid=True,
                        requires_approval=True,
                        violation_type="UNTRUSTED_CONTENT_INFLUENCE",
                        reason=f"Tool call '{tool_name}' references command found in untrusted content.",
                        policy_triggered="no_tool_from_untrusted",
                    )

        # ---------------------------------------------------------------------
        # Policy 5: max_untrusted_influence
        # ---------------------------------------------------------------------
        if self.untrusted_influence_depth > self.max_untrusted_influence:
            logger.warning(
                f"[Security Policy] Max untrusted influence depth exceeded ({self.untrusted_influence_depth} > {self.max_untrusted_influence}) for tool '{tool_name}'"
            )
            return ValidationResult(
                is_valid=True,
                requires_approval=True,
                violation_type="UNTRUSTED_INFLUENCE_EXCEEDED",
                reason=f"Execution requires explicit confirmation: {self.untrusted_influence_depth} consecutive tool calls triggered by untrusted content.",
                policy_triggered="max_untrusted_influence",
            )

        # ---------------------------------------------------------------------
        # Policy 6: Capability Authorization Check (#34)
        # ---------------------------------------------------------------------
        if self.capability_resolver and identity:
            capabilities = self.capability_resolver.resolve_capabilities(identity)
            domain = (
                "shell"
                if "terminal" in tool_lower
                else ("filesystem" if "file" in tool_lower else "tools")
            )
            action = (
                "execute"
                if "terminal" in tool_lower
                else ("write" if "write" in tool_lower else "read")
            )
            resource = cmd_str if domain == "shell" else str(arguments.get("path", "*"))

            has_cap = any(
                c.matches_domain(domain)
                and c.matches_action(action)
                and c.matches_resource(resource)
                for c in capabilities
            )
            if not has_cap and identity.role not in (Role.ADMIN, Role.SYSTEM):
                return ValidationResult(
                    is_valid=False,
                    violation_type="CAPABILITY_DENIED",
                    reason=f"Identity '{identity.user_id}' lacks capability for domain '{domain}', action '{action}'.",
                    policy_triggered="no_privilege_escalation",
                )

        return ValidationResult(is_valid=True)
