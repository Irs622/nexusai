"""API Stability Annotations & Decorators for NexusAI SDK."""

from typing import Any, TypeVar

T = TypeVar("T", bound=Any)


def stable(obj: T) -> T:
    """Decorator marking a class, method, or function as Guaranteed Stable API."""
    setattr(obj, "__api_status__", "stable")
    return obj


def experimental(obj: T) -> T:
    """Decorator marking a class, method, or function as Experimental API (May Change)."""
    setattr(obj, "__api_status__", "experimental")
    return obj


def internal(obj: T) -> T:
    """Decorator marking a class, method, or function as Internal API (No Stability Guarantee)."""
    setattr(obj, "__api_status__", "internal")
    return obj
