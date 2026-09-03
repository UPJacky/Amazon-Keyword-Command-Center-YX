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
        normalized.append({"image_id": image_id, "url": url, "position": image.get("position", index), "observations": [], "provider_calls": 0})
    return {"schema_version": "image-group-0.1", "group_id": group_id, "images": normalized, "provider_calls": 0}


def build_checklist(*, image_group_id: str, competitor_group_id: str | None = None) -> dict[str, Any]:
    return {"schema_version": "listing-checklist-0.1", "image_group_id": image_group_id, "competitor_group_id": competitor_group_id, "items": [dict(item, status="unknown", evidence=[]) for item in CHECKLIST], "ai_status": "not_requested"}


def diagnose_conversion_gap(row: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    score = row.get("market_opportunity_score")
    cvr = row.get("cvr")
    high_opportunity = score is not None and float(score) >= float(config["market"]["high_opportunity_min"])
    low_conversion = cvr is not None and float(cvr) < float(config["diagnostics"]["low_cvr"])
    return {"keyword": row.get("keyword"), "triggered": high_opportunity and low_conversion, "reason": "high_opportunity_low_cvr" if high_opportunity and low_conversion else None, "checklist_refs": ["hero_value_prop", "benefit_proof"] if high_opportunity and low_conversion else [], "facts": {"market_opportunity_score": score, "cvr": cvr}, "provider_calls": 0}
