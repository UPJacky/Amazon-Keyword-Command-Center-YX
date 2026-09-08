"""Build a buyer decision checklist from explicit evidence sources."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


def build_buyer_checklist(*, candidates: Iterable[Mapping[str, Any]], source_refs: Mapping[str, Iterable[str]] | None = None, confirmation_version: str | None = None) -> dict[str, Any]:
    refs = source_refs or {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        element_id = str(candidate.get("element_id") or "").strip()
        name = str(candidate.get("name") or candidate.get("element_name") or "").strip()
        if not element_id or not name or element_id in seen:
            continue
        seen.add(element_id)
        source = [str(value) for value in (candidate.get("source_refs") or refs.get(element_id) or []) if str(value).strip()]
        row = {
            "element_id": element_id,
            "name": name,
            "english_name": candidate.get("english_name"),
            "why_buyer_cares": candidate.get("why_buyer_cares"),
            "source_refs": deepcopy(source),
            "priority": candidate.get("priority") or len(rows) + 1,
            "confirmation_version": confirmation_version,
            "confirmed": confirmation_version is not None,
        }
        if not source:
            row["evidence_status"] = "source_missing"
        else:
            row["evidence_status"] = "supported"
        rows.append(row)
        if len(rows) == 7:
            break
    if not rows:
        return {"schema_version": "buyer-checklist-0.1", "status": "not_generated", "reason": "no_evidence_backed_candidates", "items": [], "confirmation_version": confirmation_version}
    status = "ready" if confirmation_version is not None and all(row["evidence_status"] == "supported" for row in rows) else "draft"
    return {"schema_version": "buyer-checklist-0.1", "status": status, "reason": "confirmed_checklist" if status == "ready" else "confirmation_required", "items": rows, "confirmation_version": confirmation_version, "provider_calls": 0}
