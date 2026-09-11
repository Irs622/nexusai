"""Fine-grained Capability-Based Tool Authorization System for NexusAI."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from nexusai.security.identity import Identity, Role


@dataclass(frozen=True)
class Capability:
    """A specific fine-grained permission granted to an identity.

    Attributes:
        domain: Target capability domain (e.g. "filesystem", "shell", "network", "mcp", "memory", "applescript", "*").
        action: Permitted action (e.g. "read", "write", "execute", "connect", "http_get", "invoke", "*").
        resource: Resource URI or pattern (e.g. "/workspace/**", "git", "pytest", "*.pypi.org", "*").
        constraints: Optional constraint parameters (e.g. {"max_duration_seconds": 30}).
    """

    domain: str
    action: str
    resource: str
    constraints: dict[str, Any] = field(default_factory=dict, hash=False)

    def __hash__(self) -> int:
        constraint_items = tuple(sorted((k, str(v)) for k, v in self.constraints.items()))
        return hash((self.domain, self.action, self.resource, constraint_items))

    def matches_domain(self, requested_domain: str) -> bool:
        """Check if capability covers requested domain."""
        return self.domain == "*" or self.domain.lower() == requested_domain.lower()

    def matches_action(self, requested_action: str) -> bool:
        """Check if capability covers requested action."""
        if self.action == "*":
            return True
        req = requested_action.lower()
        if "," in self.action:
            allowed = [a.strip().lower() for a in self.action.split(",")]
            return req in allowed
        return self.action.lower() == req

    def matches_resource(self, requested_resource: str) -> bool:
        """Check if capability pattern covers requested resource string."""
        if self.resource == "*":
            return True

        pat = self.resource
        req = requested_resource

        if pat == req:
            return True

        # Recursive directory wildcard handling (e.g. /workspace/** matches /workspace and /workspace/sub/file)
        if pat.endswith("/**"):
            base = pat[:-3].rstrip("/")
            if req == base or req.startswith(base + "/"):
                return True
            return False

        # Single-level directory wildcard handling (e.g. /data/*)
        if pat.endswith("/*"):
            base = pat[:-2].rstrip("/")
            if req.startswith(base + "/"):
                rel = req[len(base) + 1 :]
                return "/" not in rel
            return False

        return fnmatch.fnmatch(req, pat)

    def check_constraints(self, context: dict[str, Any] | None) -> tuple[bool, str | None]:
        """Verify that runtime execution parameters satisfy capability constraints."""
        if not self.constraints or not context:
            return True, None

        # 1. max_duration_seconds
        if "max_duration_seconds" in self.constraints and "duration_seconds" in context:
            max_sec = float(self.constraints["max_duration_seconds"])
            actual_sec = float(context["duration_seconds"])
            if actual_sec > max_sec:
                return (
                    False,
                    f"Constraint violated: duration {actual_sec}s exceeds max_duration_seconds {max_sec}s",
                )

        # 2. max_file_size / max_file_size_bytes
        max_bytes_val = self.constraints.get(
            "max_file_size_bytes", self.constraints.get("max_file_size")
        )
        if max_bytes_val is not None:
            actual_bytes = context.get("file_size_bytes", context.get("file_size"))
            if actual_bytes is not None and int(actual_bytes) > int(max_bytes_val):
                return (
                    False,
                    f"Constraint violated: file size {actual_bytes} bytes exceeds maximum {max_bytes_val} bytes",
                )

        # 3. allowed_extensions
        if "allowed_extensions" in self.constraints and "extension" in context:
            allowed_exts = set(self.constraints["allowed_extensions"])
            actual_ext = str(context["extension"]).lower().lstrip(".")
            if actual_ext not in {e.lower().lstrip(".") for e in allowed_exts}:
                return (
                    False,
                    f"Constraint violated: extension '{actual_ext}' not in allowed_extensions {allowed_exts}",
                )

        # 4. allowed_commands
        if "allowed_commands" in self.constraints and "command" in context:
            allowed_cmds = set(self.constraints["allowed_commands"])
            actual_cmd = str(context["command"]).strip().split()[0]
            if actual_cmd not in allowed_cmds:
                return (
                    False,
                    f"Constraint violated: command '{actual_cmd}' not in allowed_commands {allowed_cmds}",
                )

        # 5. allowed_ports
        if "allowed_ports" in self.constraints and "port" in context:
            allowed_ports = set(self.constraints["allowed_ports"])
            actual_port = int(context["port"])
            if actual_port not in allowed_ports:
                return (
                    False,
                    f"Constraint violated: port {actual_port} not in allowed_ports {allowed_ports}",
                )

        # 6. max_depth
        if "max_depth" in self.constraints and "depth" in context:
            max_depth = int(self.constraints["max_depth"])
            actual_depth = int(context["depth"])
            if actual_depth > max_depth:
                return (
                    False,
                    f"Constraint violated: depth {actual_depth} exceeds max_depth {max_depth}",
                )

        # 7. allowed_methods
        if "allowed_methods" in self.constraints and "method" in context:
            allowed_methods = {str(m).upper() for m in self.constraints["allowed_methods"]}
            actual_method = str(context["method"]).upper()
            if actual_method not in allowed_methods:
                return (
                    False,
                    f"Constraint violated: method '{actual_method}' not in allowed_methods {allowed_methods}",
                )

        # 8. max_redirects
        if "max_redirects" in self.constraints and "redirects" in context:
            max_redirs = int(self.constraints["max_redirects"])
            actual_redirs = int(context["redirects"])
            if actual_redirs > max_redirs:
                return (
                    False,
                    f"Constraint violated: redirects {actual_redirs} exceeds max_redirects {max_redirs}",
                )

        # 9. allowed_subpaths
        if "allowed_subpaths" in self.constraints:
            allowed_subpaths = [str(s) for s in self.constraints["allowed_subpaths"]]
            target_path_raw = context.get("path", context.get("subpath"))
            if target_path_raw is not None:
                target_posix = Path(str(target_path_raw)).as_posix()
                if not any(
                    target_posix == sub or target_posix.startswith(sub.rstrip("/") + "/")
                    for sub in allowed_subpaths
                ):
                    return (
                        False,
                        f"Constraint violated: path '{target_path_raw}' not in allowed_subpaths {allowed_subpaths}",
                    )

        # 10. no_pipe
        if self.constraints.get("no_pipe") and "command" in context:
            cmd_val = str(context["command"])
            if "|" in cmd_val:
                return (
                    False,
                    "Constraint violated: pipeline execution (|) forbidden by no_pipe constraint",
                )

        # 11. no_redirect
        if self.constraints.get("no_redirect") and "command" in context:
            cmd_val = str(context["command"])
            if ">" in cmd_val or "<" in cmd_val:
                return (
                    False,
                    "Constraint violated: I/O redirection (<, >) forbidden by no_redirect constraint",
                )

        # 12. max_request_size
        if "max_request_size" in self.constraints:
            max_req = int(self.constraints["max_request_size"])
            actual_req = context.get(
                "request_size", context.get("body_size", context.get("content_length"))
            )
            if actual_req is not None and int(actual_req) > max_req:
                return (
                    False,
                    f"Constraint violated: request size {actual_req} bytes exceeds max_request_size {max_req} bytes",
                )

        # 13. risk_level_max
        if "risk_level_max" in self.constraints and "risk_level" in context:
            risk_hierarchy = {"LOW": 10, "MEDIUM": 20, "HIGH": 30, "CRITICAL": 40}
            max_risk_str = str(self.constraints["risk_level_max"]).upper()
            actual_risk_str = (
                str(context["risk_level"]).upper().removeprefix("RISKLEVEL.").removeprefix("RISK_")
            )
            if risk_hierarchy.get(actual_risk_str, 0) > risk_hierarchy.get(max_risk_str, 0):
                return (
                    False,
                    f"Constraint violated: risk level '{actual_risk_str}' exceeds risk_level_max '{max_risk_str}'",
                )

        # 14. max_results
        if "max_results" in self.constraints:
            max_res = int(self.constraints["max_results"])
            actual_res = context.get("limit", context.get("max_results"))
            if actual_res is not None and int(actual_res) > max_res:
                return (
                    False,
                    f"Constraint violated: results limit {actual_res} exceeds max_results {max_res}",
                )

        return True, None


@dataclass
class CapabilityProfile:
    """Named bundle of positive capabilities representing an agent persona or security tier."""

    name: str
    description: str = ""
    capabilities: list[Capability] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)


class CapabilityResolver:
    """Resolves and evaluates positive capabilities for authenticated identities.

    Implements a default-deny capability authorization engine with profile inheritance.
    """

    def __init__(
        self,
        profiles: dict[str, CapabilityProfile] | None = None,
        role_profile_mapping: dict[Role, str] | None = None,
        user_profile_mapping: dict[str, str] | None = None,
        default_profile: str = "default",
    ) -> None:
        self.profiles: dict[str, CapabilityProfile] = profiles or {}
        self.role_profile_mapping: dict[Role, str] = role_profile_mapping or {
            Role.ADMIN: "unrestricted_admin",
            Role.SYSTEM: "unrestricted_admin",
            Role.OPERATOR: "coding_agent",
            Role.VIEWER: "readonly_agent",
        }
        self.user_profile_mapping: dict[str, str] = user_profile_mapping or {}
        self.default_profile = default_profile

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> CapabilityResolver:
        """Load capability profiles from a YAML configuration file."""
        p = Path(yaml_path)
        if not p.is_file():
            logger.warning(
                f"Capabilities YAML file '{yaml_path}' not found. Using default built-in profiles."
            )
            return cls.build_default_resolver()

        try:
            content = p.read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
        except Exception as e:
            logger.error(
                f"Error reading capabilities file '{yaml_path}': {e}. Falling back to defaults."
            )
            return cls.build_default_resolver()

        profiles: dict[str, CapabilityProfile] = {}
        raw_profiles = data.get("profiles", {})

        for name, p_data in raw_profiles.items():
            desc = p_data.get("description", "")
            raw_extends = p_data.get("extends", [])
            extends_list = (
                [str(raw_extends)]
                if isinstance(raw_extends, str)
                else [str(e) for e in raw_extends]
            )

            caps_list: list[Capability] = []
            for cap_def in p_data.get("capabilities", []):
                domain = str(cap_def.get("domain", "*"))
                actions = cap_def.get("action", "*")
                resources = cap_def.get("resource", "*")
                constraints = cap_def.get("constraints", {})

                # Expand action list or single string
                action_str = ",".join(actions) if isinstance(actions, list) else str(actions)

                # Expand resource list into individual capabilities
                if isinstance(resources, list):
                    for res in resources:
                        caps_list.append(
                            Capability(
                                domain=domain,
                                action=action_str,
                                resource=str(res),
                                constraints=dict(constraints) if constraints else {},
                            )
                        )
                else:
                    caps_list.append(
                        Capability(
                            domain=domain,
                            action=action_str,
                            resource=str(resources),
                            constraints=dict(constraints) if constraints else {},
                        )
                    )

            profiles[name] = CapabilityProfile(
                name=name, description=desc, capabilities=caps_list, extends=extends_list
            )

        # Ensure standard profiles exist if not in yaml
        default_resolver = cls.build_default_resolver()
        for def_name, def_prof in default_resolver.profiles.items():
            if def_name not in profiles:
                profiles[def_name] = def_prof

        return cls(profiles=profiles)

    @classmethod
    def build_default_resolver(cls) -> CapabilityResolver:
        """Construct standard built-in capability profiles."""
        profiles = {
            "unrestricted_admin": CapabilityProfile(
                name="unrestricted_admin",
                description="Unrestricted administrative access to all domains, actions, and resources",
                capabilities=[
                    Capability(domain="*", action="*", resource="*"),
                ],
            ),
            "coding_agent": CapabilityProfile(
                name="coding_agent",
                description="Software engineering agent profile with workspace file access and curated shell tools",
                extends=["readonly_agent"],
                capabilities=[
                    Capability(
                        domain="filesystem",
                        action="write",
                        resource="/workspace/**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="write",
                        resource="./**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="write",
                        resource="/tmp/**",
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="git",
                        constraints={"max_duration_seconds": 120},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="pytest",
                        constraints={"max_duration_seconds": 180},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="python",
                        constraints={"max_duration_seconds": 120},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="pip",
                        constraints={"max_duration_seconds": 120},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="ls",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="cat",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="echo",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="grep",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="find",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="mkdir",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="touch",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="head",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="shell",
                        action="execute",
                        resource="tail",
                        constraints={"max_duration_seconds": 30},
                    ),
                    Capability(
                        domain="tool",
                        action="execute",
                        resource="*",
                    ),
                    Capability(
                        domain="network",
                        action="http_get",
                        resource="*.pypi.org",
                    ),
                    Capability(
                        domain="memory",
                        action="write",
                        resource="*",
                    ),
                ],
            ),
            "readonly_agent": CapabilityProfile(
                name="readonly_agent",
                description="Read-only observation and audit agent",
                capabilities=[
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="/workspace/**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="./**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="/tmp/**",
                    ),
                    Capability(
                        domain="tool",
                        action="execute",
                        resource="*",
                    ),
                    Capability(
                        domain="memory",
                        action="read,search",
                        resource="*",
                    ),
                ],
            ),
            "default": CapabilityProfile(
                name="default",
                description="Default baseline capabilities for standard operations",
                capabilities=[
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="/workspace/**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="./**",
                    ),
                    Capability(
                        domain="filesystem",
                        action="read,list",
                        resource="/tmp/**",
                    ),
                    Capability(
                        domain="tool",
                        action="execute",
                        resource="*",
                    ),
                    Capability(
                        domain="memory",
                        action="read",
                        resource="*",
                    ),
                ],
            ),
        }
        return cls(profiles=profiles)

    def resolve_profile_capabilities(
        self, profile_name: str, seen: set[str] | None = None
    ) -> list[Capability]:
        """Recursively resolve effective capabilities for a profile, inheriting from extended profiles."""
        if seen is None:
            seen = set()
        if profile_name in seen or profile_name not in self.profiles:
            return []
        seen.add(profile_name)

        prof = self.profiles[profile_name]
        accumulated: list[Capability] = []

        # 1. Inherit from parent profiles
        for parent_name in prof.extends:
            accumulated.extend(self.resolve_profile_capabilities(parent_name, seen))

        # 2. Add profile's own capabilities
        accumulated.extend(prof.capabilities)

        # Deduplicate while preserving order
        unique_caps: list[Capability] = []
        for c in accumulated:
            if c not in unique_caps:
                unique_caps.append(c)
        return unique_caps

    def resolve_capabilities(self, identity: Identity) -> list[Capability]:
        """Resolve the effective list of positive capabilities granted to an identity."""
        # 1. Explicit capabilities passed in identity metadata
        meta_caps = identity.metadata.get("capabilities")
        if isinstance(meta_caps, (list, tuple)) and meta_caps:
            resolved: list[Capability] = []
            for c in meta_caps:
                if isinstance(c, Capability):
                    resolved.append(c)
                elif isinstance(c, dict):
                    resolved.append(
                        Capability(
                            domain=str(c.get("domain", "*")),
                            action=str(c.get("action", "*")),
                            resource=str(c.get("resource", "*")),
                            constraints=dict(c.get("constraints", {})),
                        )
                    )
            return resolved

        # 2. Specific capability profile named in identity metadata
        profile_name = identity.metadata.get("capability_profile")
        if profile_name and profile_name in self.profiles:
            return self.resolve_profile_capabilities(profile_name)

        # 3. User ID specific mapping
        if identity.user_id in self.user_profile_mapping:
            u_prof = self.user_profile_mapping[identity.user_id]
            if u_prof in self.profiles:
                return self.resolve_profile_capabilities(u_prof)

        # 4. Role-based profile mapping
        if identity.role in self.role_profile_mapping:
            r_prof = self.role_profile_mapping[identity.role]
            if r_prof in self.profiles:
                return self.resolve_profile_capabilities(r_prof)

        # 5. Fallback default profile
        if self.default_profile in self.profiles:
            return self.resolve_profile_capabilities(self.default_profile)

        return []

    def evaluate(
        self,
        identity: Identity,
        domain: str,
        action: str,
        resource: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, Capability | None, str | None]:
        """Evaluate whether identity possesses positive capability for the requested action.

        Returns:
            tuple of (is_allowed, matched_capability_or_none, denial_reason_or_none).
        """
        granted = self.resolve_capabilities(identity)
        if not granted:
            return (
                False,
                None,
                f"Identity '{identity.user_id}' (role: {identity.role.value}) has no granted capabilities",
            )

        for cap in granted:
            if not cap.matches_domain(domain):
                continue
            if not cap.matches_action(action):
                continue
            if not cap.matches_resource(resource):
                continue

            # Check runtime constraints
            satisfied, constraint_err = cap.check_constraints(context)
            if not satisfied:
                return False, None, constraint_err

            return True, cap, None

        return (
            False,
            None,
            f"Capability denied: Identity '{identity.user_id}' lacks capability for domain '{domain}', action '{action}' on resource '{resource}'",
        )
