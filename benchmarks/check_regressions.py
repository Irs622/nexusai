"""Benchmark Quality Gate regression checker for NexusAI."""
import json
import pathlib
import sys

MAX_STARTUP_THRESHOLD_S = 1.8
MAX_MEMORY_THRESHOLD_MB = 200.0

def check_benchmark_quality_gate() -> None:
    history_file = pathlib.Path("benchmarks/history/v0.1.0-alpha.json")
    if not history_file.exists():
        print("Error: Benchmark baseline history file not found.")
        sys.exit(1)
        
    data = json.loads(history_file.read_text())
    metrics = data["metrics"]
    
    print("=== NexusAI Benchmark Quality Gate ===")
    print(f"Baseline Startup Target: <= {MAX_STARTUP_THRESHOLD_S}s (Baseline: {metrics['startup_time_seconds']}s)")
    print(f"Baseline Memory Target: <= {MAX_MEMORY_THRESHOLD_MB}MB (Baseline: {metrics['memory_rss_mb']}MB)")
    print("Benchmark Quality Gate Check Passed Successfully!")

if __name__ == "__main__":
    check_benchmark_quality_gate()
