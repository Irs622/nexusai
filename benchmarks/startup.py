"""Cold start execution benchmark for NexusAI."""
import time
import subprocess

def measure_startup() -> float:
    start_time = time.perf_counter()
    result = subprocess.run(
        [".venv/bin/python", "-m", "nexusai.cli.app", "--help"],
        capture_output=True,
        text=True
    )
    end_time = time.perf_counter()
    duration = end_time - start_time
    assert result.returncode == 0
    return duration

if __name__ == "__main__":
    duration = measure_startup()
    print(f"CLI Cold Start Benchmark Time: {duration:.4f} seconds")
