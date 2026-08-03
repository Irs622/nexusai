"""Memory footprint benchmark for NexusAI."""
import os
import psutil

def measure_memory_footprint() -> float:
    process = psutil.Process(os.getpid())
    rss_mb = process.memory_info().rss / (1024 * 1024)
    return rss_mb

if __name__ == "__main__":
    import nexusai.cli.app # Load modules
    rss_mb = measure_memory_footprint()
    print(f"Memory Footprint (RSS): {rss_mb:.2f} MB")
