"""Build a buyer decision checklist from explicit evidence sources."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _confirmation_item_ids(confirmation: Mapping[str, Any]) -> list[str] | None:
    """Extract the confirmed scope without treating arbitrary text as proof."""
    raw = confirmation.get("confirmed_feature_ids")
    if raw is None:
        raw = confirmation.get("confirmed_item_ids")
    if raw is None:
        raw = confirmation.get("items")
    if not isinstance(raw, list):
        return None
    ids: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = item.get("element_id") or item.get("feature_id") or item.get("item_id")
        else:
            value = item
        value = _text(value)
        if value is None:
            return None
        ids.append(value)
    return ids


def _validate_confirmation(confirmation: Mapping[str, Any] | None,
                           expected_version: str | None,
                           item_ids: set[str]) -> tuple[bool, str, dict[str, Any] | None]:
    """Validate the server-returned confirmation at the consumer boundary.

    A version string is only a label.  It is deliberately insufficient to
    mark evidence ready; the worker must receive the immutable confirmed row
    from the task identity it claimed.
    """
    if not isinstance(confirmation, Mapping):
        return False, "confirmation_required", None
    if confirmation.get("status") != "confirmed":
        return False, "confirmation_not_confirmed", None
    version = _text(confirmation.get("version") or confirmation.get("confirmation_version"))
    if expected_version is None or version != expected_version:
        return False, "confirmation_version_mismatch", None
    ids = _confirmation_item_ids(confirmation)
    if ids is None or len(ids) != len(set(ids)) or set(ids) != item_ids:
        return False, "confirmation_items_mismatch", None
    # The SQL boundary binds these fields to the claimed task.  Require them
    # here as well when a structured record is supplied, so an injected dict
    # cannot silently become a production confirmation.
    required_identity = ("object_id", "task_id", "store_id", "self_asin", "input_hash")
    if any(_text(confirmation.get(field)) is None for field in required_identity):
        return False, "confirmation_identity_missing", None
    input_hash = _text(confirmation.get("input_hash"))
    if input_hash is None or len(input_hash) != 64 or any(char not in "0123456789abcdefABCDEF" for char in input_hash):
        return False, "confirmation_hash_invalid", None
    return True, "confirmed_checklist", {
        key: confirmation[key] for key in (
            "confirmation_id", "object_id", "version", "status", "task_id",
            "store_id", "self_asin", "input_hash", "confirmed_by", "confirmed_at",
        ) if key in confirmation
    }


def build_buyer_checklist(*, candidates: Iterable[Mapping[str, Any]], source_refs: Mapping[str, Iterable[str]] | None = None,
                          confirmation_version: str | None = None,
                          confirmation: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
            "confirmation_version": None,
            "confirmed": False,
        }
        if not source:
            row["evidence_status"] = "source_missing"
        else:
            row["evidence_status"] = "supported"
        rows.append(row)
        if len(rows) == 7:
            break
    expected_version = _text(confirmation_version)
    if not rows:
        return {"schema_version": "buyer-checklist-0.1", "status": "not_generated", "reason": "no_evidence_backed_candidates", "items": [], "confirmation_version": expected_version}
    valid, reason, confirmation_meta = _validate_confirmation(
        confirmation, expected_version, {row["element_id"] for row in rows})
    evidence_ready = all(row["evidence_status"] == "supported" for row in rows)
    ready = valid and evidence_ready
    if ready:
        for row in rows:
            row["confirmation_version"] = expected_version
            row["confirmed"] = True
    result = {"schema_version": "buyer-checklist-0.1", "status": "ready" if ready else "draft",
              "reason": reason if not ready else "confirmed_checklist", "items": rows,
              "confirmation_version": expected_version, "provider_calls": 0,
              "confirmation_valid": valid}
    if confirmation_meta is not None:
        result["confirmation"] = confirmation_meta
    return result
