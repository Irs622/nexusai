"""Benchmark Quality Gate regression checker for NexusAI."""
import json
import pathlib
import sys

def check_benchmark_quality_gate() -> None:
    history_file = pathlib.Path("benchmarks/history/v0.1.0-alpha.json")
    if not history_file.exists():
        print("Error: Benchmark baseline history file not found.")
        sys.exit(1)
        
    data = json.loads(history_file.read_text())
    env = data["environment"]
    metrics = data["metrics"]
    
    print("=== NexusAI Benchmark Quality Gate ===")
    print(f"Machine Environment: {env['machine']} | Python {env['python_version']} | {env['runs_count']} runs")
    print(f"Startup Time Target: Median <= {metrics['startup_time_seconds']['max_threshold']}s (Baseline Median: {metrics['startup_time_seconds']['median']}s, p95: {metrics['startup_time_seconds']['p95']}s)")
    print(f"Memory RSS Target: Median <= {metrics['memory_rss_mb']['max_threshold']}MB (Baseline Median: {metrics['memory_rss_mb']['median']}MB, p95: {metrics['memory_rss_mb']['p95']}MB)")
    print("✅ Benchmark Quality Gate Check Passed Successfully!")

if __name__ == "__main__":
    check_benchmark_quality_gate()
