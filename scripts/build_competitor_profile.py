#!/usr/bin/env python3
"""Build a local competitors.json artifact from reviewed metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.competitors.profile import build_competitor_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON metadata with self_asin and competitors")
    parser.add_argument("--output", required=True, help="competitors.json path")
    args = parser.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    profile = build_competitor_profile(
        self_asin=source["self_asin"],
        competitors=source["competitors"],
        core_keywords=source.get("core_keywords", []),
        marketplace=source.get("marketplace", "US"),
        snapshot_version=source.get("snapshot_version"),
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": True, "competitor_count": len(profile["competitors"]), "provider_calls": profile["provider_calls"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
