"""Tests for the canonical CircuitBreaker and its deprecated aliases (ADR 0037)."""

import importlib

import pytest

from nexusai.providers.circuit_breaker import CircuitBreaker, CircuitState
from nexusai.providers.clock import TestClock as FakeClock
from nexusai.providers.exceptions import ProviderCircuitOpenError


async def _fail() -> None:
    raise ValueError("boom")


async def _ok() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_canonical_full_lifecycle_with_injected_clock() -> None:
    clock = FakeClock()
    cb = CircuitBreaker("p1", failure_threshold=2, recovery_timeout_seconds=10.0, clock=clock)

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(_fail)
    assert cb.state == CircuitState.OPEN
    assert cb.trip_count == 1
    assert cb.can_execute() is False
    with pytest.raises(ProviderCircuitOpenError):
        await cb.call(_ok)

    clock.advance(11.0)
    assert cb.state == CircuitState.HALF_OPEN
    assert await cb.call(_ok) == "ok"
    assert cb.state == CircuitState.HALF_OPEN  # success_threshold defaults to 2
    await cb.call(_ok)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    metrics = cb.get_metrics()
    assert metrics["state"] == "closed"
    assert metrics["total_failures"] == 2
    assert metrics["sliding_window_sample_size"] == 4


def test_half_open_failure_reopens_and_counts_trip() -> None:
    clock = FakeClock()
    cb = CircuitBreaker("p1", failure_threshold=1, recovery_timeout_seconds=1.0, clock=clock)
    cb.record_failure()
    clock.advance(2.0)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.trip_count == 2


def test_sliding_window_is_bounded() -> None:
    cb = CircuitBreaker("p1", failure_threshold=100, sliding_window_size=3)
    for _ in range(5):
        cb.record_success(latency_ms=10.0)
    assert cb.get_metrics()["sliding_window_sample_size"] == 3


@pytest.mark.parametrize(
    "module_name", ["nexusai.runtime.circuit_breaker", "nexusai.models.circuit_breaker"]
)
def test_deprecated_aliases_warn_and_resolve_to_canonical(module_name: str) -> None:
    module = importlib.import_module(module_name)
    with pytest.warns(DeprecationWarning, match="nexusai.providers.circuit_breaker"):
        alias_cls = module.CircuitBreaker
    with pytest.warns(DeprecationWarning):
        assert module.CircuitState is CircuitState
    assert issubclass(alias_cls, CircuitBreaker)


def test_runtime_package_export_is_canonical_without_warning() -> None:
    import warnings

    import nexusai.runtime as runtime_pkg

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert runtime_pkg.CircuitBreaker is CircuitBreaker
        assert runtime_pkg.CircuitState is CircuitState


def test_models_alias_keeps_legacy_defaults() -> None:
    with pytest.warns(DeprecationWarning):
        from nexusai.models.circuit_breaker import CircuitBreaker as Legacy

    clock = FakeClock()
    cb = Legacy(failure_threshold=1, recovery_timeout_seconds=1.0, clock=clock)
    assert cb.provider_id == "default_provider"
    cb.record_failure(latency_ms=50.0)
    assert cb.get_metrics()["state"] == "OPEN"
    clock.advance(2.0)
    assert cb.can_execute() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED  # one success closes, as before


def test_unknown_alias_attribute_raises() -> None:
    module = importlib.import_module("nexusai.runtime.circuit_breaker")
    with pytest.raises(AttributeError):
        _ = module.DoesNotExist
