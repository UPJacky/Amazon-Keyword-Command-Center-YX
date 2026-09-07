#!/usr/bin/env python3
"""Build Provider-neutral listing diagnostics from reviewed local metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.diagnostics.listing_checklist import build_listing_diagnostics
from worker.rule_engine.engine import load_default_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload = build_listing_diagnostics(self_images=source.get("self_images", []), competitor_images=source.get("competitor_images", []), keyword_rows=source.get("keyword_rows", []), config=load_default_config())
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": True, "checklist_items": len(payload["checklist"]["items"]), "provider_calls": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
