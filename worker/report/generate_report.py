"""Assemble parser output and deterministic rule results into a report."""

from __future__ import annotations

import json
import os
import uuid
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from worker.ingestion.ad_report_parser import parse_report
from worker.rule_engine.engine import evaluate_keyword, load_default_config, load_json
from worker.providers.market_merge import merge_market_data
from worker.providers.config_validation import validate_config
from worker.report.traceability import normalise_missing_fields


RULE_VERSION = "rule-v0.1"
REPORT_SCHEMA_VERSION = "report-0.2"


def shared_traceability(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable report-0.2 lineage shared by every artifact."""
    reconciliation = report.get("reconciliation") or {}
    return {
        "schema_version": report.get("schema_version"),
        "input_file": report.get("input_file"),
        "input_sha256": report.get("input_sha256"),
        "currency_code": report.get("currency_code"),
        "rule_version": report.get("rule_version"),
        "config_version": report.get("config_version"),
        "provider_snapshot_version": report.get("provider_snapshot_version"),
        "reconciliation_passed": reconciliation.get("passed") is True,
        "missing_fields": report_missing_fields(report),
    }


def report_missing_fields(report: Mapping[str, Any]) -> list[str]:
    """Summarize row-level missingness for task-page traceability.

    Keep the projection deterministic for hand-built Provider fixtures while
    enforcing the report contract's standard string field names.
    """
    fields: set[str] = set()
    for row in report.get("rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        fields.update(normalise_missing_fields(row.get("missing_fields")))
    return sorted(fields)


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish a report artifact once; never replace historical output."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"report artifact already exists: {path.name}") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def _sort_key(row: Mapping[str, Any], group_order: Mapping[str, int]) -> tuple[Any, ...]:
    volume = row.get("market_search_volume")
    return (
        group_order.get(row.get("ui_color", "gray"), 999),
        volume is None,
        -(float(volume) if volume is not None else 0),
        -float(row.get("spend") or 0),
        unicodedata.normalize("NFC", str(row.get("keyword") or "")).casefold(),
        unicodedata.normalize("NFC", str(row.get("keyword") or "")),
        str(row.get("keyword") or ""),
    )


def build_report(input_path: str | Path, output_dir: str | Path, config: Mapping[str, Any] | None = None, market_rows: list[Mapping[str, Any]] | None = None, provider_snapshot_version: str | None = None) -> dict[str, Any]:
    parsed = parse_report(input_path)
    if not parsed["reconciliation"]["passed"]:
        raise ValueError("reconciliation failed; report generation stopped")
    effective_config = dict(config or load_default_config())
    config_errors = validate_config(effective_config)
    if config_errors:
        raise ValueError("invalid configuration: " + "; ".join(config_errors))
    mapping = load_json(Path(__file__).resolve().parents[2] / "rules" / "definitions" / "action_mapping.json")
    group_order = {color: index for index, color in enumerate(mapping["display_order"])}
    rows: list[dict[str, Any]] = []
    inputs = merge_market_data(parsed["aggregated_rows"], market_rows or [])
    for aggregated in inputs:
        result = evaluate_keyword(aggregated, effective_config)
        rows.append({**aggregated, **result, "rule_version": RULE_VERSION})
    rows.sort(key=lambda row: _sort_key(row, group_order))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["action_group"]] = counts.get(row["action_group"], 0) + 1
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "input_file": parsed["input_file"],
        "input_sha256": parsed["input_sha256"],
        "rule_version": RULE_VERSION,
        "config_version": effective_config.get("config_version", effective_config.get("schema_version", "unknown")),
        "provider_snapshot_version": provider_snapshot_version,
        "currency_code": parsed["currency_code"],
        "reconciliation": parsed["reconciliation"],
        "summary": {"keyword_count": len(rows), "action_group_counts": counts},
        "rows": rows,
    }
    report["missing_fields"] = report_missing_fields(report)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_new_json(destination / "master-table.json", report)
    shared = shared_traceability(report)
    action_results = {
        **shared,
        "rows": rows,
    }
    _write_new_json(destination / "action-results.json", action_results)
    _write_new_json(destination / "report-meta.json", shared)
    return report
