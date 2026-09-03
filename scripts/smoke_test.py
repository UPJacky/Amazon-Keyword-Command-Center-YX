#!/usr/bin/env python3
"""End-to-end local smoke test; uses no network and no secrets."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.queue.file_queue import FileQueue
from worker.queue.runner import run_one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="data/fixtures/商品推广_搜索词_报告_LED演示.xlsx")
    args = parser.parse_args()
    fixture = Path(args.fixture).resolve()
    if not fixture.is_file():
        print(json.dumps({"passed": False, "error": "fixture not found"}, ensure_ascii=False))
        return 1
    with tempfile.TemporaryDirectory(prefix="kwcc-smoke-") as directory:
        root = Path(directory)
        queue_root = root / "queue"
        storage_root = root / "storage"
        FileQueue(queue_root).enqueue({"task_id": "smoke-task", "run_id": "smoke-run", "input_path": str(fixture)})
        result = run_one(queue_root, storage_root)
        report = storage_root / "smoke-task" / "smoke-run" / "master-table.json"
        passed = bool(result and result["status"] == "completed" and report.is_file())
        output = {"passed": passed, "result": result, "report_exists": report.is_file(), "network_calls": 0}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

