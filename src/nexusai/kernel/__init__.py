"""
Kernel package re-exports for NexusAI OS Kernel Orchestration Engine.
"""

from __future__ import annotations

from nexusai.kernel.bootstrap import KernelBootstrap
from nexusai.kernel.contracts import KernelService, ServiceDescriptor, ServiceLifecycleState
from nexusai.kernel.dependency_graph import RuntimeDependencyGraph
from nexusai.kernel.lifecycle import LifecycleCoordinator
from nexusai.kernel.migration import MigrationPlan, MigrationRunner, MigrationStep, SchemaVersion
from nexusai.kernel.orchestrator import KernelOrchestrator
from nexusai.kernel.registry import ServiceRegistry
from nexusai.kernel.scheduler import RuntimeScheduler
from nexusai.kernel.snapshot import KernelSnapshot, SnapshotManager
from nexusai.kernel.transaction import AsyncTransaction, UnitOfWork
from nexusai.kernel.worker import BackgroundWorkerManager

__all__ = [
    "AsyncTransaction",
    "BackgroundWorkerManager",
    "KernelBootstrap",
    "KernelOrchestrator",
    "KernelService",
    "KernelSnapshot",
    "LifecycleCoordinator",
    "MigrationPlan",
    "MigrationRunner",
    "MigrationStep",
    "RuntimeDependencyGraph",
    "RuntimeScheduler",
    "SchemaVersion",
    "ServiceDescriptor",
    "ServiceLifecycleState",
    "ServiceRegistry",
    "SnapshotManager",
    "UnitOfWork",
]
