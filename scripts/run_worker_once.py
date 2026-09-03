#!/usr/bin/env python3
"""Run at most one local queue item; designed for a future process supervisor."""

import argparse
import json
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.queue.runner import run_one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-root", required=True)
    parser.add_argument("--storage-root", required=True)
    args = parser.parse_args()
    result = run_one(args.queue_root, args.storage_root)
    if result is None:
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())

