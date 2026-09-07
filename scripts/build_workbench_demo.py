#!/usr/bin/env python3
"""Rebuild three public, offline workbench fixtures from reviewed golden JSON.

Run before build_pages_demo.py. No image is fetched or interpreted: the
existing builders run unchanged, then example-domain image placeholders are
removed from the public projection. IDs, empty evidence and unknown facts stay
intact. Output uses stable ordering and contains no clock-dependent values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_pages_demo import EXTERNAL_URL_PATTERN, SECRET_PATTERN
from worker.competitors.profile import build_competitor_profile
from worker.diagnostics.listing_checklist import build_checklist, build_image_group, diagnose_conversion_gap
from worker.diagnostics.optimization import build_optimization_plan
from worker.security.path_guard import contains_link_or_reparse


ARTIFACT_FILES = ("competitors.json", "listing-diagnostics.json", "optimization-plan.json")
DEFAULT_OUTPUT = ROOT / "data/golden/market-demo-modules"
COMPETITOR_INPUT = "data/golden/competitor-input-demo.json"
LISTING_INPUT = "data/golden/listing-diagnostics-input-demo.json"
REPORT_INPUT = "data/golden/market-demo-report/master-table.json"
CONFIG_INPUT = "rules/defaults/stable.json"
PLACEHOLDER_IMAGE_URL = re.compile(
    r"https?://example\.(?:invalid|test|com|net|org)(?:[/?#][^\s]*)?", re.I
)


def _read_input(relative: str) -> tuple[dict, dict]:
    path = ROOT / relative
    if contains_link_or_reparse(path):
        raise ValueError(f"fixture input must not contain a symbolic link: {relative}")
    raw = path.read_bytes()
    # Normalize line endings so checkout settings do not change provenance.
    canonical = raw.replace(b"\r\n", b"\n")
    return json.loads(raw), {
        "path": relative,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "hash_normalization": "utf8-lf",
    }


def _mark_demo(payload: dict, source: str, inputs: list[dict], builders: list[str]) -> dict:
    return dict(payload, demo=True, fixture_source=source, fixture_inputs=inputs,
                fixture_builders=builders, provider_calls=0, network_calls=0,
                external_calls=0, local_only=True)


def build_payloads() -> dict[str, dict]:
    competitor, competitor_ref = _read_input(COMPETITOR_INPUT)
    listing, listing_ref = _read_input(LISTING_INPUT)
    report, report_ref = _read_input(REPORT_INPUT)
    config, config_ref = _read_input(CONFIG_INPUT)

    profile = build_competitor_profile(
        self_asin=competitor["self_asin"], competitors=competitor["competitors"],
        core_keywords=competitor.get("core_keywords", []),
        marketplace=competitor.get("marketplace", "US"),
        snapshot_version=competitor.get("snapshot_version"),
    )
    for row in profile["competitors"]:
        row["image_urls"] = [url for url in row["image_urls"]
                             if not PLACEHOLDER_IMAGE_URL.fullmatch(url)]

    self_group = build_image_group(listing.get("self_images", []), group_id="self-images")
    competitor_group = build_image_group(listing.get("competitor_images", []), group_id="competitor-images")
    for group in (self_group, competitor_group):
        for image in group["images"]:
            if PLACEHOLDER_IMAGE_URL.fullmatch(image["url"]):
                image["url"] = None
    diagnostics = {
        "schema_version": "listing-diagnostics-0.1",
        "self_images": self_group,
        "competitor_images": competitor_group,
        "checklist": build_checklist(image_group_id="self-images", competitor_group_id="competitor-images"),
        "conversion_diagnostics": [diagnose_conversion_gap(row, config)
                                   for row in listing.get("keyword_rows", [])],
    }
    optimization = {
        "schema_version": "optimization-plan-0.2",
        "ai_may_change_action": False,
        "entity_diagnosis_contract": "entity_context_required_for_judgement",
        "actions": build_optimization_plan(report["rows"], config),
    }
    return {
        "competitors.json": _mark_demo(profile, COMPETITOR_INPUT, [competitor_ref],
            ["worker.competitors.profile.build_competitor_profile"]),
        "listing-diagnostics.json": _mark_demo(diagnostics, LISTING_INPUT, [listing_ref, config_ref],
            ["worker.diagnostics.listing_checklist.build_image_group",
             "worker.diagnostics.listing_checklist.build_checklist",
             "worker.diagnostics.listing_checklist.diagnose_conversion_gap"]),
        "optimization-plan.json": _mark_demo(optimization, REPORT_INPUT, [report_ref, config_ref],
            ["worker.diagnostics.optimization.build_optimization_plan"]),
    }


def build(output: str | Path = DEFAULT_OUTPUT) -> Path:
    destination = Path(output)
    if contains_link_or_reparse(destination):
        raise ValueError("output directory must not contain a symbolic link")
    payloads = build_payloads()
    serialized = {name: json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                  for name, payload in payloads.items()}
    # Do not silently sanitize arbitrary URLs or secrets in other fields.
    for name, content in serialized.items():
        if EXTERNAL_URL_PATTERN.search(content) or SECRET_PATTERN.search(content):
            raise ValueError(f"unsafe public demo content: {name}")
        target = destination / name
        if contains_link_or_reparse(target):
            raise ValueError(f"output file must not contain a symbolic link: {name}")
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, dict) or existing.get("demo") is not True or existing.get("fixture_source") != payloads[name]["fixture_source"]:
                raise ValueError(f"refusing to replace a non-demo artifact: {name}")
    destination.mkdir(parents=True, exist_ok=True)
    if contains_link_or_reparse(destination) or not destination.is_dir():
        raise ValueError("output directory must be a real directory")
    for name, content in serialized.items():
        if contains_link_or_reparse(destination / name):
            raise ValueError(f"output file must not contain a symbolic link: {name}")
        (destination / name).write_text(content, encoding="utf-8", newline="\n")
    return destination.resolve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Directory for the three generated demo JSON files")
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({"passed": True, "output": str(result), "files": list(ARTIFACT_FILES),
                      "provider_calls": 0, "network_calls": 0, "external_calls": 0,
                      "local_only": True}, ensure_ascii=False))
