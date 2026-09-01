#!/usr/bin/env python3
"""P5-LIVE Staging Validation Harness CLI Runner.

Supports:
  python tools/run_p5_live.py --mode preflight
  python tools/run_p5_live.py --mode dry-run
  python tools/run_p5_live.py --mode execute
  python tools/run_p5_live.py --mode execute --scenario P5-LIVE-01
"""

from __future__ import annotations

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
    parser.add_argument(
        "--scenario", default=None, help="Specific scenario ID to run (e.g. P5-LIVE-01)"
    )
    parser.add_argument(
        "--output-artifact",
        default="artifacts/p5_live/p5_live_evidence_report.json",
        help="Path to save evidence JSON artifact",
    )

    args = parser.parse_args()

    harness = P5LiveHarness(cluster_id=args.cluster, namespace=args.namespace)

    try:
        res = asyncio.run(harness.run_mode(args.mode, scenario_filter=args.scenario))

        # If execute mode without single scenario filter, persist artifact report
        if args.mode == "execute" and not args.scenario:
            out_path = Path(args.output_artifact)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
            print(f"[P5-LIVE] Wrote evidence report artifact to: {out_path}", file=sys.stderr)

        print(json.dumps(res, indent=2))
        return (
            0
            if res.get("verdict") == "PASS" or res.get("status") in ("PASSED", "DRY_RUN_PASSED")
            else 1
        )
    except Exception as err:
        print(f"P5-LIVE Execution Failure ({args.mode}): {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
