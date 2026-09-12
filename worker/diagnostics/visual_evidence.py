"""Validate structured visual observations; never infer missing images as absent."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


ANSWER_MODES = {"direct_visual", "text_or_icon", "not_seen", "unknown"}
PROMINENCE = {"dominant", "supporting", "small", "unknown"}
LEGIBILITY = {"clear", "uncertain", "unreadable"}
CONFIDENCE = {"high", "medium", "low"}


def build_visual_evidence(*, image_ids: Iterable[str], observations: Iterable[Mapping[str, Any]], expected_element_ids: Iterable[str], evidence_version: str) -> dict[str, Any]:
    expected_images = [str(value) for value in image_ids if str(value).strip()]
    expected_elements = [str(value) for value in expected_element_ids if str(value).strip()]
    if not expected_images or not expected_elements:
        return {"schema_version": "visual-evidence-0.1", "status": "not_generated", "reason": "image_or_element_scope_missing", "observations": []}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for observation in observations:
        if not isinstance(observation, Mapping):
            errors.append("observation_not_object")
            continue
        row = {key: observation.get(key) for key in ("image_id", "element_id", "evidence_region", "visible_objects", "visible_text", "answer_mode", "prominence", "legibility", "confidence", "source_refs")}
        if row["image_id"] not in expected_images or row["element_id"] not in expected_elements:
            errors.append("unknown_image_or_element")
            continue
        if row["answer_mode"] not in ANSWER_MODES or row["prominence"] not in PROMINENCE or row["legibility"] not in LEGIBILITY or row["confidence"] not in CONFIDENCE:
            errors.append("observation_enum_invalid")
            continue
        row["evidence_version"] = evidence_version
        rows.append(row)
    keys = {(row["image_id"], row["element_id"]) for row in rows}
    expected_keys = {(image_id, element_id) for image_id in expected_images for element_id in expected_elements}
    if len(keys) != len(rows):
        errors.append("duplicate_image_element")
    missing = sorted(expected_keys - keys)
    not_judged = [row for row in rows if row["answer_mode"] == "unknown" or row["prominence"] == "unknown" or row["legibility"] == "unreadable" or not row.get("evidence_region") or not isinstance(row.get("source_refs"), list) or not row.get("source_refs")]
    if not_judged:
        errors.append("observation_not_judged")
    status = "ready" if not errors and not missing else "partial" if rows else "failed"
    return {"schema_version": "visual-evidence-0.1", "status": status, "reason": "complete_observation" if status == "ready" else "observation_incomplete", "expected_image_ids": expected_images, "expected_element_ids": expected_elements, "observations": rows, "missing_image_element": [[image, element] for image, element in missing], "errors": errors, "provider_calls": 0}
