"""
KernelService base class, ServiceDescriptor, and probes (re-exported from contracts).
"""

from __future__ import annotations

from nexusai.kernel.contracts import (
    KernelService,
    ServiceDescriptor,
    ServiceLifecycleState,
)

__all__ = [
    "KernelService",
    "ServiceDescriptor",
    "ServiceLifecycleState",
]
