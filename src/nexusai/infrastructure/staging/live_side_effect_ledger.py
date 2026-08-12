"""Non-authoritative real side-effect evidence collector with cryptographic SHA-256 hash chains."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping


class LiveSideEffectCollector:
    """Non-authoritative observable side-effect evidence collector."""

    def __init__(self) -> None:
        self.evidence_records: list[dict[str, Any]] = []
        self.last_hash: str = "0000000000000000000000000000000000000000000000000000000000000000"
        self.observed_idempotency_keys: dict[str, list[dict[str, Any]]] = {}

    def record_observed_side_effect(
        self,
        scenario_id: str,
        execution_id: str,
        attempt_id: str,
        idempotency_key: str,
        worker_id: str,
        fencing_token: int,
        recovery_epoch: int,
        committed: bool,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an observed external side-effect transaction and append to SHA-256 hash chain."""
        timestamp = time.time()

        record = {
            "scenario_id": scenario_id,
            "execution_id": execution_id,
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "worker_id": worker_id,
            "fencing_token": fencing_token,
            "recovery_epoch": recovery_epoch,
            "committed": committed,
            "timestamp": timestamp,
            "details": details or {},
            "previous_hash": self.last_hash,
        }

        # Calculate SHA-256 hash of this record
        serialized = json.dumps(record, sort_keys=True)
        current_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        record["hash"] = current_hash

        self.last_hash = current_hash
        self.evidence_records.append(record)

        if committed:
            if idempotency_key not in self.observed_idempotency_keys:
                self.observed_idempotency_keys[idempotency_key] = []
            self.observed_idempotency_keys[idempotency_key].append(record)

        return record

    def get_committed_side_effects_count(self, idempotency_key: str) -> int:
        """Return count of committed side effects observed for a given idempotency key."""
        return len(self.observed_idempotency_keys.get(idempotency_key, []))

    def verify_evidence_hash_chain(self) -> bool:
        """Verify structural integrity of SHA-256 tamper-evident evidence hash chain."""
        prev = "0000000000000000000000000000000000000000000000000000000000000000"
        for rec in self.evidence_records:
            if rec["previous_hash"] != prev:
                return False
            rec_copy = dict(rec)
            expected_hash = rec_copy.pop("hash")
            serialized = json.dumps(rec_copy, sort_keys=True)
            calc_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            if calc_hash != expected_hash:
                return False
            prev = expected_hash
        return True
