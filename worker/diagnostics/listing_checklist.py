"""Deterministic listing checklist; visual recognition is intentionally injectable."""

from __future__ import annotations

import re
from typing import Any, Mapping


IMAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

CHECKLIST = (
    {"check_id": "hero_value_prop", "category": "message", "question": "主图是否在首屏表达核心价值", "severity": "high"},
    {"check_id": "mobile_readability", "category": "image", "question": "移动端缩略图是否仍可读", "severity": "medium"},
    {"check_id": "benefit_proof", "category": "proof", "question": "卖点是否有清晰场景或证据支撑", "severity": "high"},
    {"check_id": "competitor_difference", "category": "positioning", "question": "是否能看出与竞品的关键差异", "severity": "medium"},
)


def build_image_group(images: list[Mapping[str, Any]], *, group_id: str) -> dict[str, Any]:
    if not IMAGE_ID.fullmatch(group_id):
        raise ValueError("group_id must be a safe identifier")
    normalized: list[dict[str, Any]] = []
    for index, image in enumerate(images, start=1):
        image_id = str(image.get("image_id") or f"image-{index}")
        if not IMAGE_ID.fullmatch(image_id):
            raise ValueError("image_id must be a safe identifier")
        url = image.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("image url is required")
        observations = image.get("observations", [])
        if not isinstance(observations, list) or any(not isinstance(item, Mapping) for item in observations):
            raise ValueError("image observations must be an array of objects")
        calls = image.get("provider_calls", 0)
        if type(calls) is not int or calls < 0:
            raise ValueError("image provider_calls must be a non-negative integer")
        row = {"image_id": image_id, "url": url, "position": image.get("position", index),
               "observations": [dict(item) for item in observations], "provider_calls": calls}
        for field in ("source", "sampled_at", "observation_status"):
            if field in image:
                row[field] = image[field]
        normalized.append(row)
    return {"schema_version": "image-group-0.2", "group_id": group_id, "images": normalized,
            "provider_calls": sum(item["provider_calls"] for item in normalized),
            "observation_status": "ready" if any(item["observations"] for item in normalized) else "not_requested"}


def build_checklist(*, image_group_id: str, competitor_group_id: str | None = None, evaluations: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    evaluations = evaluations if isinstance(evaluations, Mapping) else {}
    items = []
    for base in CHECKLIST:
        supplied = evaluations.get(base["check_id"], {})
        if not isinstance(supplied, Mapping):
            supplied = {}
        evidence = supplied.get("evidence", [])
        if not isinstance(evidence, list) or any(item in (None, "") for item in evidence):
            evidence = []
        status = supplied.get("status") if supplied.get("status") in {"pass", "fail", "unknown"} else "unknown"
        # A conclusion without evidence is not a conclusion. This prevents an
        # injected model label or placeholder from being reported as success.
        if status != "unknown" and not evidence:
            status = "unknown"
        items.append(dict(base, status=status, evidence=evidence))
    ai_status = "completed" if any(item["status"] in {"pass", "fail"} for item in items) else "not_requested"
    return {"schema_version": "listing-checklist-0.2", "image_group_id": image_group_id,
            "competitor_group_id": competitor_group_id, "items": items, "ai_status": ai_status}


def build_listing_diagnostics(*, self_images: list[Mapping[str, Any]], competitor_images: list[Mapping[str, Any]], config: Mapping[str, Any], keyword_rows: list[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Build a private, provider-neutral listing artifact from supplied evidence."""
    self_group = build_image_group(self_images, group_id="self-images")
    competitor_group = build_image_group(competitor_images, group_id="competitor-images")
    provider_calls = self_group["provider_calls"] + competitor_group["provider_calls"]
    status = "ready" if self_group["observation_status"] == "ready" else "partial"
    return {
        "schema_version": "listing-diagnostics-0.2",
        "module_status": {"status": status, "reason": "visual_observations_present" if status == "ready" else "image_observations_not_available"},
        "self_images": self_group,
        "competitor_images": competitor_group,
        "checklist": build_checklist(image_group_id="self-images", competitor_group_id="competitor-images"),
        "conversion_diagnostics": [diagnose_conversion_gap(row, config) for row in keyword_rows],
        "provider_calls": provider_calls,
    }


def diagnose_conversion_gap(row: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    score = row.get("market_opportunity_score")
    cvr = row.get("cvr")
    high_opportunity = score is not None and float(score) >= float(config["market"]["high_opportunity_min"])
    low_conversion = cvr is not None and float(cvr) < float(config["diagnostics"]["low_cvr"])
    return {"keyword": row.get("keyword"), "triggered": high_opportunity and low_conversion, "reason": "high_opportunity_low_cvr" if high_opportunity and low_conversion else None, "checklist_refs": ["hero_value_prop", "benefit_proof"] if high_opportunity and low_conversion else [], "facts": {"market_opportunity_score": score, "cvr": cvr}, "provider_calls": 0}
