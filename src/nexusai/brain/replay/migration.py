"""Replay Schema Migration Registry for ExecutionLog version transitions."""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class ISchemaMigration(Protocol):
    """Protocol interface for transforming raw ExecutionLog JSON structures across schema versions."""

    def migrate(
        self, header: dict[str, Any], events: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Migrate header and events data from schema version N to version N+1."""
        ...


class MigrationRegistry:
    """Registry maintaining migration functions across ExecutionLog schema versions with pipeline chaining and validation hooks."""

    def __init__(self) -> None:
        self._migrations: dict[
            tuple[int, int],
            Callable[
                [dict[str, Any], list[dict[str, Any]]], tuple[dict[str, Any], list[dict[str, Any]]]
            ],
        ] = {}
        self._validators: dict[int, Callable[[dict[str, Any], list[dict[str, Any]]], bool]] = {}

    def register_migration(
        self,
        from_version: int,
        to_version: int,
        migration_fn: Callable[
            [dict[str, Any], list[dict[str, Any]]], tuple[dict[str, Any], list[dict[str, Any]]]
        ],
    ) -> None:
        """Register a schema migration function."""
        self._migrations[(from_version, to_version)] = migration_fn

    def register_validator(
        self, version: int, validator_fn: Callable[[dict[str, Any], list[dict[str, Any]]], bool]
    ) -> None:
        """Register a schema version validation function."""
        self._validators[version] = validator_fn

    def validate_log(
        self, header: dict[str, Any], events: list[dict[str, Any]], version: int
    ) -> bool:
        """Validate header and events against schema version rules."""
        if version in self._validators:
            return self._validators[version](header, events)
        return True

    def migrate_log(
        self, header: dict[str, Any], events: list[dict[str, Any]], target_version: int = 1
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Migrate raw log JSON structures from current version up to target_version via pipeline chaining."""
        current_version = int(header.get("schema_version", 1))
        curr_header = dict(header)
        curr_events = list(events)

        while current_version < target_version:
            next_version = current_version + 1
            key = (current_version, next_version)
            if key not in self._migrations:
                raise ValueError(
                    f"No registered migration step for schema version transition {current_version} -> {next_version}"
                )
            migration_fn = self._migrations[key]
            curr_header, curr_events = migration_fn(curr_header, curr_events)
            curr_header["schema_version"] = next_version

            if not self.validate_log(curr_header, curr_events, next_version):
                raise ValueError(
                    f"Migration validation failed for target schema version {next_version}"
                )

            current_version = next_version

        return curr_header, curr_events
