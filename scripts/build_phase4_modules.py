#!/usr/bin/env python3
"""Build Phase 4 local module artifacts from an existing report JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.report.modules import build_negative_keywords, build_rank_benchmark
from worker.rule_engine.engine import load_default_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="master-table.json")
    parser.add_argument("--output", required=True, help="output directory")
    parser.add_argument("--my-asin")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = report.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("report rows must be an array")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rank = build_rank_benchmark(rows, my_asin=args.my_asin)
    negative = build_negative_keywords(rows, load_default_config())
    (output / "rank-benchmark.json").write_text(json.dumps({"schema_version": "module02-0.1", "rows": rank}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (output / "negative-keywords.json").write_text(json.dumps({"schema_version": "module03-0.1", "write_back": False, **negative}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": True, "rank_rows": len(rank), "negative_candidates": sum(len(items) for items in negative.values()), "write_back": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
