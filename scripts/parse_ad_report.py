#!/usr/bin/env python3
"""CLI for deterministic Amazon ad report parsing."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.ingestion.ad_report_parser import ParseError, parse_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        result = parse_report(args.input_file, args.output_dir)
    except ParseError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"passed": result["reconciliation"]["passed"], "output_dir": args.output_dir, "summary": result["reconciliation"]}, ensure_ascii=False, indent=2))
    return 0 if result["reconciliation"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
