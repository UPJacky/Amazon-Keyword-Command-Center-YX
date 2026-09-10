"""Deterministic competitor image comparison and designer brief contracts.

The provider may supply observations, but it may not decide a product winner or
silently invent a feature.  This module only validates and projects evidence
that is explicitly bound to one competitor, one competitor image and one own
image.  A brief is actionable text for a designer; it never writes to Amazon.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


COMPARISON_STATUSES = {"到位", "弱", "未知"}
BRIEF_FIELDS = (
    "self_image_id", "label", "existing_expression", "weak_elements",
    "keep_content", "composition", "subject", "text_hierarchy",
    "english_copy_draft", "keywords", "references", "truth_constraints",
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_id(value: Any, allowed: set[str], label: str) -> str:
    item = _text(value)
    if not item or item not in allowed:
        raise ValueError(f"{label} must reference an existing image")
    return item


def _source_refs(value: Any) -> list[str]:
    refs = [item.strip() for item in _list(value) if isinstance(item, str) and item.strip()]
    return list(dict.fromkeys(refs))


def _normalize_comparison(
    row: Mapping[str, Any], *, self_image_ids: set[str], competitor_image_ids: set[str],
    competitor_asins: set[str], expected_element_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("comparison must be an object")
    asin = _text(row.get("competitor_asin")).upper()
    if asin not in competitor_asins:
        raise ValueError("comparison must reference one selected competitor")
    element_id = _text(row.get("element_id"))
    if not element_id or (expected_element_ids and element_id not in expected_element_ids):
        raise ValueError("comparison element_id is not in the confirmed checklist")
    result = str(row.get("status") or "未知")
    if result not in COMPARISON_STATUSES:
        raise ValueError("comparison status must be 到位, 弱 or 未知")
    own_image = _safe_id(row.get("target_self_image_id"), self_image_ids, "target_self_image_id")
    reference_image = _safe_id(row.get("reference_competitor_image_id"), competitor_image_ids, "reference_competitor_image_id")
    evidence = _source_refs(row.get("evidence"))
    if result != "未知" and not evidence:
        raise ValueError("到位/弱 comparison requires evidence")
    return {
        "competitor_asin": asin,
        "element_id": element_id,
        "status": result,
        "target_self_image_id": own_image,
        "reference_competitor_image_id": reference_image,
        "evidence": evidence,
        "borrowing_method": _text(row.get("borrowing_method")),
        "specific_change": _text(row.get("specific_change")),
        "source_refs": _source_refs(row.get("source_refs")),
    }


def _normalize_brief(row: Mapping[str, Any], *, self_image_ids: set[str], competitor_image_ids: set[str], competitor_asins: set[str]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise ValueError("image brief must be an object")
    normalized: dict[str, Any] = {
        "self_image_id": _safe_id(row.get("self_image_id"), self_image_ids, "self_image_id"),
        "label": _text(row.get("label")),
        "existing_expression": _text(row.get("existing_expression")),
        "weak_elements": _list(row.get("weak_elements")),
        "keep_content": _list(row.get("keep_content")),
        "composition": _text(row.get("composition")),
        "subject": _text(row.get("subject")),
        "text_hierarchy": _text(row.get("text_hierarchy")),
        "english_copy_draft": _text(row.get("english_copy_draft")),
        "keywords": _list(row.get("keywords")),
        "truth_constraints": _list(row.get("truth_constraints")),
    }
    refs = []
    for reference in _list(row.get("references")):
        if not isinstance(reference, Mapping):
            raise ValueError("brief reference must be an object")
        asin = _text(reference.get("competitor_asin")).upper()
        image_id = _safe_id(reference.get("image_id"), competitor_image_ids, "brief reference image_id")
        if asin not in competitor_asins:
            raise ValueError("brief reference competitor is not selected")
        refs.append({"competitor_asin": asin, "image_id": image_id, "reason": _text(reference.get("reason"))})
    normalized["references"] = refs
    normalized["source_refs"] = _source_refs(row.get("source_refs"))
    if not normalized["label"]:
        raise ValueError("image brief label is required")
    return normalized


def build_visual_brief(
    *, self_image_ids: Iterable[str], competitor_image_ids: Iterable[str],
    competitor_asins: Iterable[str], expected_element_ids: Iterable[str],
    comparisons: Iterable[Mapping[str, Any]] = (), briefs: Iterable[Mapping[str, Any]] = (),
    version: str = "visual-brief-v1",
) -> dict[str, Any]:
    self_ids = {str(item) for item in self_image_ids if str(item)}
    competitor_ids = {str(item) for item in competitor_image_ids if str(item)}
    asins = {str(item).upper() for item in competitor_asins if str(item)}
    elements = {str(item) for item in expected_element_ids if str(item)}
    if not _text(version):
        raise ValueError("visual brief version is required")
    comparison_rows = [_normalize_comparison(
        row, self_image_ids=self_ids, competitor_image_ids=competitor_ids,
        competitor_asins=asins, expected_element_ids=elements,
    ) for row in comparisons]
    brief_rows = [_normalize_brief(
        row, self_image_ids=self_ids, competitor_image_ids=competitor_ids,
        competitor_asins=asins,
    ) for row in briefs]
    if len({row["self_image_id"] for row in brief_rows}) != len(brief_rows):
        raise ValueError("one brief is allowed per self image")
    covered_self = {row["self_image_id"] for row in brief_rows}
    complete_briefs = bool(self_ids) and covered_self == self_ids
    comparison_ready = bool(comparison_rows) and all(row["status"] != "未知" for row in comparison_rows)
    status = "ready" if complete_briefs and comparison_ready else "partial"
    reason = "comparison_and_brief_complete" if status == "ready" else "comparison_or_brief_incomplete"
    return {
        "schema_version": "visual-brief-0.1",
        "version": version,
        "module_status": {"status": status, "reason": reason},
        "comparison_scope": "one_competitor_per_row",
        "comparisons": comparison_rows,
        "briefs": brief_rows,
        "coverage": {
            "self_images_expected": len(self_ids), "self_images_briefed": len(covered_self),
            "comparison_rows": len(comparison_rows), "competitors_referenced": sorted({row["competitor_asin"] for row in comparison_rows}),
        },
    }
