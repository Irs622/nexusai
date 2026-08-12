"""Centralized performance metrics collection, latency percentile calculation, and JSON exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
import time
from typing import Any, Sequence


@dataclass
class PerformanceMetrics:
    """Collector for operations count, throughput, latencies, and percentiles."""

    benchmark_name: str
    workers: int = 1
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    timeout_operations: int = 0
    sqlite_contention_count: int = 0
    security_violations: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def record_operation(self, duration_ms: float, success: bool = True, is_timeout: bool = False) -> None:
        self.total_operations += 1
        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1
        if is_timeout:
            self.timeout_operations += 1
        self.latencies_ms.append(duration_ms)

    def finalize(self) -> None:
        if self.end_time == 0.0:
            self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return max(end - self.start_time, 0.001)

    @property
    def throughput_ops_per_sec(self) -> float:
        return self.total_operations / self.duration_seconds

    def get_percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = int(math.ceil((p / 100.0) * len(sorted_lats))) - 1
        return sorted_lats[max(0, min(idx, len(sorted_lats) - 1))]

    def to_dict(self) -> dict[str, Any]:
        self.finalize()
        lats = self.latencies_ms or [0.0]
        return {
            "benchmark": self.benchmark_name,
            "workers": self.workers,
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "timeout_operations": self.timeout_operations,
            "sqlite_contention_count": self.sqlite_contention_count,
            "security_violations": self.security_violations,
            "duration_seconds": round(self.duration_seconds, 3),
            "throughput_ops_sec": round(self.throughput_ops_per_sec, 2),
            "latency_ms": {
                "min": round(min(lats), 3),
                "mean": round(sum(lats) / len(lats), 3),
                "p50": round(self.get_percentile(50.0), 3),
                "p95": round(self.get_percentile(95.0), 3),
                "p99": round(self.get_percentile(99.0), 3),
                "max": round(max(lats), 3),
            },
        }

    def export_json(self, output_path: str = "artifacts/p4_8/performance_results.json") -> None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        data = self.to_dict()

        # Append or write JSON array
        existing_records = []
        if os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing_records = json.load(f)
                    if not isinstance(existing_records, list):
                        existing_records = []
            except Exception:
                existing_records = []

        existing_records.append(data)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(existing_records, f, indent=2)
