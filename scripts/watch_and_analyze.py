#!/usr/bin/env python3
"""Watch the Redis scan queue and run analysis when all jobs complete.

Usage (on Pi5):
    python scripts/watch_and_analyze.py --results-dir /data/results/prospect

Or from docker:
    docker compose exec worker python scripts/watch_and_analyze.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import redis
except ImportError:
    print("ERROR: redis package required. pip install redis", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Watch queue and analyze when done")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--results-dir", type=Path, default=Path("/data/results/prospect"))
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between queue checks")
    args = parser.parse_args()

    r = redis.Redis.from_url(args.redis_url, decode_responses=True)
    r.ping()

    print(f"Watching queue:scan (polling every {args.poll_interval}s)...")
    print(f"Results dir: {args.results_dir}")

    prev_len = -1
    stable_count = 0

    while True:
        queue_len = r.llen("queue:scan")

        if queue_len != prev_len:
            print(f"  Queue: {queue_len} jobs remaining")
            prev_len = queue_len
            stable_count = 0
        else:
            stable_count += 1

        # Queue is empty and has been for 2 polls (workers finished)
        if queue_len == 0 and stable_count >= 2:
            print("\nQueue empty — all jobs processed. Running analysis...\n")
            break

        time.sleep(args.poll_interval)

    # Run analysis
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from analyze_results import load_results, analyze, print_report

    results = load_results(args.results_dir)
    if not results:
        print("No results found.", file=sys.stderr)
        sys.exit(1)

    stats = analyze(results)
    print_report(stats)

    # Also write JSON
    json_path = args.results_dir / "analysis.json"
    with open(json_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nJSON analysis written to {json_path}")


if __name__ == "__main__":
    main()
