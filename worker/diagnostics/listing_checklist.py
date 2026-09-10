"""Deterministic listing checklist; visual recognition is intentionally injectable."""

from __future__ import annotations

import re
from typing import Any, Mapping

from worker.diagnostics.visual_evidence import build_visual_evidence
from worker.diagnostics.visual_brief import build_visual_brief


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
            # Raw observations have not been validated against the confirmed
            # image/element scope. Presence alone cannot establish coverage.
            "observation_status": "partial" if any(item["observations"] for item in normalized) else "not_requested"}


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


def _attach_visual_observations(images: list[Mapping[str, Any]], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows_by_image: dict[str, list[dict[str, Any]]] = {}
    for row in evidence.get("observations", []):
        if isinstance(row, Mapping):
            rows_by_image.setdefault(str(row.get("image_id")), []).append(dict(row))
    result = []
    for image in images:
        item = dict(image)
        observations = list(item.get("observations") or [])
        observations.extend(rows_by_image.get(str(item.get("image_id")), []))
        item["observations"] = observations
        result.append(item)
    return result


def _normalize_visual_evidence(*, image_ids: list[str], visual_evidence: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if visual_evidence is None:
        return None
    if not isinstance(visual_evidence, Mapping):
        raise ValueError("visual evidence must be an object")
    expected_elements = visual_evidence.get("expected_element_ids")
    observations = visual_evidence.get("observations")
    version = visual_evidence.get("evidence_version") or visual_evidence.get("version")
    if not isinstance(expected_elements, list) or not isinstance(observations, list) or not isinstance(version, str) or not version.strip():
        raise ValueError("visual evidence requires expected elements, observations and version")
    return build_visual_evidence(
        image_ids=image_ids,
        observations=observations,
        expected_element_ids=expected_elements,
        evidence_version=version,
    )


def build_listing_diagnostics(*, self_images: list[Mapping[str, Any]], competitor_images: list[Mapping[str, Any]], config: Mapping[str, Any], keyword_rows: list[Mapping[str, Any]] = (), visual_evidence: Mapping[str, Any] | None = None, checklist_evaluations: Mapping[str, Mapping[str, Any]] | None = None, competitor_comparisons: list[Mapping[str, Any]] | None = None, image_briefs: list[Mapping[str, Any]] | None = None, competitor_asins: list[str] | None = None) -> dict[str, Any]:
    """Build a private, provider-neutral listing artifact from supplied evidence."""
    self_group = build_image_group(self_images, group_id="self-images")
    competitor_group = build_image_group(competitor_images, group_id="competitor-images")
    all_image_ids = [item["image_id"] for item in self_group["images"] + competitor_group["images"]]
    normalized_evidence = _normalize_visual_evidence(image_ids=all_image_ids, visual_evidence=visual_evidence)
    if normalized_evidence is not None:
        self_group = build_image_group(_attach_visual_observations(self_group["images"], normalized_evidence), group_id="self-images")
        competitor_group = build_image_group(_attach_visual_observations(competitor_group["images"], normalized_evidence), group_id="competitor-images")
    provider_calls = self_group["provider_calls"] + competitor_group["provider_calls"]
    checklist = build_checklist(
        image_group_id="self-images", competitor_group_id="competitor-images",
        evaluations=checklist_evaluations,
    )
    evidence_ready = normalized_evidence is not None and normalized_evidence["status"] == "ready"
    checklist_ready = all(item["status"] in {"pass", "fail"} for item in checklist["items"])
    expected_elements = normalized_evidence.get("expected_element_ids", []) if normalized_evidence else []
    brief_input = competitor_comparisons is not None or image_briefs is not None
    if brief_input:
        visual_brief = build_visual_brief(
            self_image_ids=[item["image_id"] for item in self_group["images"]],
            competitor_image_ids=[item["image_id"] for item in competitor_group["images"]],
            competitor_asins=competitor_asins or [],
            expected_element_ids=expected_elements,
            comparisons=competitor_comparisons or [],
            briefs=image_briefs or [],
        )
    else:
        visual_brief = {
            "schema_version": "visual-brief-0.1",
            "version": "visual-brief-v1",
            "module_status": {"status": "not_generated", "reason": "comparison_and_brief_not_available"},
            "comparison_scope": "one_competitor_per_row",
            "comparisons": [], "briefs": [],
            "coverage": {"self_images_expected": len(self_group["images"]), "self_images_briefed": 0, "comparison_rows": 0, "competitors_referenced": []},
        }
    brief_ready = visual_brief["module_status"]["status"] == "ready"
    if normalized_evidence is not None and normalized_evidence["status"] == "failed":
        status, reason = "failed", "visual_provider_evidence_invalid"
    elif evidence_ready and checklist_ready and brief_ready:
        status, reason = "ready", "visual_evidence_and_checklist_complete"
    elif normalized_evidence is not None:
        status, reason = "partial", "visual_evidence_incomplete_or_checklist_unconfirmed"
    else:
        status, reason = "partial", "image_observations_not_available"
    return {
        "schema_version": "listing-diagnostics-0.2",
        "module_status": {"status": status, "reason": reason},
        "self_images": self_group,
        "competitor_images": competitor_group,
        "checklist": checklist,
        "visual_brief": visual_brief,
        "conversion_diagnostics": [diagnose_conversion_gap(row, config) for row in keyword_rows],
        "provider_calls": provider_calls + (normalized_evidence.get("provider_calls", 0) if normalized_evidence else 0),
    }


def diagnose_conversion_gap(row: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    score = row.get("market_opportunity_score")
    cvr = row.get("cvr")
    high_opportunity = score is not None and float(score) >= float(config["market"]["high_opportunity_min"])
    low_conversion = cvr is not None and float(cvr) < float(config["diagnostics"]["low_cvr"])
    return {"keyword": row.get("keyword"), "triggered": high_opportunity and low_conversion, "reason": "high_opportunity_low_cvr" if high_opportunity and low_conversion else None, "checklist_refs": ["hero_value_prop", "benefit_proof"] if high_opportunity and low_conversion else [], "facts": {"market_opportunity_score": score, "cvr": cvr}, "provider_calls": 0}
