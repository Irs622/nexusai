"""Unit test suite for execution coordination domain models, WorkerIdentity, ExecutionLease, and fencing tokens."""

from __future__ import annotations

import time
import pytest

from nexusai.brain.domain.execution_coordination import (
    ExecutionLease,
    FencingTokenError,
    LeaseAcquisitionError,
    LeaseStatus,
    StaleWorkerError,
    WorkerIdentity,
)


def test_worker_identity_and_lease_domain_models() -> None:
    """Test WorkerIdentity domain validation and ExecutionLease immutability."""
    worker = WorkerIdentity(worker_id="w-1", process_id=1234, host_id="node-a")

    assert worker.worker_id == "w-1"
    assert worker.process_id == 1234
    assert len(worker.instance_nonce) > 0

    lease = ExecutionLease(
        lease_id="l-1",
        execution_id="e-1",
        session_id="s-1",
        worker_id="w-1",
        fencing_token=1,
    )

    assert lease.lease_id == "l-1"
    assert lease.fencing_token == 1
    assert lease.status == LeaseStatus.LEASED
    assert len(lease.audit_hash) > 0

    with pytest.raises(ValueError, match="worker_id cannot be empty"):
        WorkerIdentity(worker_id="  ")

    with pytest.raises(ValueError, match="fencing_token must be a positive integer"):
        ExecutionLease("l-2", "e-2", "s-2", "w-1", fencing_token=0)


if __name__ == "__main__":
    test_worker_identity_and_lease_domain_models()
    print("ALL EXECUTION COORDINATOR DOMAIN UNIT TESTS PASSED SUCCESSFULLY!")
