#!/usr/bin/env python3
"""P5-LIVE Staging Validation Harness CLI Runner.

Supports:
  python tools/run_p5_live.py --mode preflight
  python tools/run_p5_live.py --mode dry-run
  python tools/run_p5_live.py --mode execute
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from tests.staging.test_p5_live_harness import P5LiveHarness


def main() -> int:
    parser = argparse.ArgumentParser(description="P5-LIVE Staging Validation Harness Runner")
    parser.add_argument(
        "--mode",
        choices=["preflight", "dry-run", "execute"],
        default="preflight",
        help="Harness execution mode (preflight, dry-run, execute)",
    )
    parser.add_argument("--cluster", default="nexusai-staging", help="Staging cluster ID")
    parser.add_argument("--namespace", default="nexusai-staging", help="Staging namespace")

    args = parser.parse_args()

    harness = P5LiveHarness(cluster_id=args.cluster, namespace=args.namespace)

    try:
        res = asyncio.run(harness.run_mode(args.mode))
        print(json.dumps(res, indent=2))
        return 0
    except Exception as err:
        print(f"P5-LIVE Execution Failure ({args.mode}): {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
