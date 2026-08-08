"""Architecture Fitness Test — Rule A007 & Field Budgets (Runtime Context & State Ownership).

Enforces field budget ceilings and verifies WorkingMemory isolation from ExecutionContext.
"""

from __future__ import annotations

import dataclasses
import inspect

from nexusai.brain.runtime.context import (
    CancellationContext,
    ExecutionContext,
    IdentityContext,
    RuntimeContext,
    SecurityContext,
    TelemetryContext,
)


def test_execution_context_field_budgets():
    """Verify ExecutionContext sub-context field budgets per AGENTS.md governance rules."""
    assert len(dataclasses.fields(IdentityContext)) <= 4, "IdentityContext exceeds 4 field limit!"
    assert len(dataclasses.fields(RuntimeContext)) <= 5, "RuntimeContext exceeds 5 field limit!"
    assert len(dataclasses.fields(SecurityContext)) <= 3, "SecurityContext exceeds 3 field limit!"
    assert len(dataclasses.fields(TelemetryContext)) <= 3, "TelemetryContext exceeds 3 field limit!"
    assert (
        len(dataclasses.fields(CancellationContext)) <= 2
    ), "CancellationContext exceeds 2 field limit!"


def test_working_memory_not_in_execution_context():
    """Verify WorkingMemory is completely decoupled from ExecutionContext and TelemetryContext."""
    exec_ctx_fields = [f.name for f in dataclasses.fields(ExecutionContext)]
    telemetry_fields = [f.name for f in dataclasses.fields(TelemetryContext)]

    assert "working_memory" not in exec_ctx_fields, "WorkingMemory must NOT be in ExecutionContext!"
    assert (
        "working_memory" not in telemetry_fields
    ), "WorkingMemory must NOT be in TelemetryContext!"

    # Verify context module source code does not import working_memory
    from nexusai.brain.runtime import context as ctx_module

    src = inspect.getsource(ctx_module)
    assert (
        "WorkingMemory" not in src
    ), "ExecutionContext source code must NOT reference WorkingMemory!"


if __name__ == "__main__":
    test_execution_context_field_budgets()
    test_working_memory_not_in_execution_context()
    print("ALL RUNTIME CONTEXT FITNESS TESTS PASSED SUCCESSFULLY!")
