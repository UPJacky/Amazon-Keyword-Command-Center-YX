"""Run one task locally with reconciliation and artifact gates."""

from __future__ import annotations

import json
import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from worker.ingestion.ad_report_parser import ParseError, parse_report
from worker.report.generate_report import build_report, shared_traceability
from worker.providers.config_validation import validate_config
from worker.rule_engine.engine import load_default_config
from worker.report.modules import build_negative_keywords, build_rank_benchmark
from worker.competitors.profile import build_competitor_profile
from worker.diagnostics.optimization import build_optimization_plan
from worker.storage.artifacts import run_root, write_json


ProviderEnricher = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
_USAGE_FIELDS = {"requested_keywords", "estimated_calls", "cache_hits", "actual_calls", "rate_limited", "failures", "requested_requests", "unique_requests", "duplicates_suppressed", "retries"}


def _provider_result(value: Any) -> tuple[list[Mapping[str, Any]], str, dict[str, int]]:
    if not isinstance(value, Mapping) or set(value) != {"market_rows", "provider_snapshot_version", "usage"}:
        raise ValueError("invalid provider enrichment shape")
    rows, version, usage = value["market_rows"], value["provider_snapshot_version"], value["usage"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("provider market rows must be a list of objects")
    if not isinstance(version, str) or not re.fullmatch(r"(?:snapshot-|provider-batch-v1-)[A-Za-z0-9_.-]{1,100}", version):
        raise ValueError("invalid provider snapshot version")
    if not isinstance(usage, Mapping) or "actual_calls" not in usage or not set(usage) <= _USAGE_FIELDS:
        raise ValueError("invalid provider usage counters")
    if any(type(counter) is not int or counter < 0 for counter in usage.values()):
        raise ValueError("invalid provider usage counter")
    # Reject non-JSON/NaN payloads before they can reach report artifacts.
    json.dumps(rows, allow_nan=False)
    return copy.deepcopy(rows), version, dict(usage)


@dataclass(frozen=True)
class TaskExecutionResult:
    task_id: str
    run_id: str
    status: str
    current_stage: str
    failure_reason: dict[str, Any] | None = None
    report_path: str | None = None


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def run_task(input_path: str | Path, storage_root: str | Path, task_id: str, run_id: str, config: Mapping[str, Any] | None = None, market_rows: list[Mapping[str, Any]] | None = None, provider_snapshot_version: str | None = None, competitor_profile: Mapping[str, Any] | None = None, provider_enricher: ProviderEnricher | None = None) -> TaskExecutionResult:
    """Run offline by default; an explicitly injected enricher runs after gates."""
    root = run_root(storage_root, task_id, run_id)
    # A run key is immutable.  Refuse a second execution before touching any
    # existing artifact, including a previous failed run's failure.json.
    if root.exists() and any(root.iterdir()):
        reason = {
            "code": "DUPLICATE_TASK_RUN",
            "message": "task_id and run_id already have artifacts; create a new run_id for a rerun",
            "stage": "task",
            "retryable": False,
        }
        return TaskExecutionResult(task_id, run_id, "failed", "task", reason)
    try:
        parsed = parse_report(input_path)
    except (ParseError, OSError) as exc:
        reason = {"code": "INPUT_INVALID", "message": str(exc), "stage": "ingestion", "retryable": False}
        _write(root / "failure.json", reason)
        return TaskExecutionResult(task_id, run_id, "failed", "ingestion", reason)

    _write(root / "ad-aggregated.json", parsed)
    _write(root / "reconciliation.json", parsed["reconciliation"])
    _write(root / "input-meta.json", {
        "schema_version": "input-meta-0.1",
        "input_file": parsed["input_file"],
        "input_sha256": parsed["input_sha256"],
        "parser_version": parsed["parser_version"],
        "currency_code": parsed["currency_code"],
        "reconciliation_passed": parsed["reconciliation"]["passed"],
    })
    if not parsed["reconciliation"]["passed"]:
        reason = {"code": "RECONCILIATION_FAILED", "message": "reconciliation did not pass; Provider and rule stages were skipped", "stage": "reconciliation", "retryable": False}
        _write(root / "failure.json", reason)
        return TaskExecutionResult(task_id, run_id, "failed", "reconciliation", reason)

    effective_config = dict(config or load_default_config())
    config_errors = validate_config(effective_config)
    if config_errors:
        reason = {"code": "CONFIG_INVALID", "message": "; ".join(config_errors), "stage": "config", "retryable": False}
        _write(root / "failure.json", reason)
        return TaskExecutionResult(task_id, run_id, "failed", "config", reason)
    validated_competitor_profile = None
    if competitor_profile is not None:
        try:
            validated_competitor_profile = build_competitor_profile(
                self_asin=str(competitor_profile["self_asin"]),
                competitors=competitor_profile["competitors"],
                core_keywords=competitor_profile.get("core_keywords", []),
                marketplace=str(competitor_profile.get("marketplace", "US")),
                snapshot_version=competitor_profile.get("snapshot_version"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            reason = {"code": "COMPETITOR_PROFILE_INVALID", "message": str(exc), "stage": "competitors", "retryable": False}
            _write(root / "failure.json", reason)
            return TaskExecutionResult(task_id, run_id, "failed", "competitors", reason)
    if provider_enricher is not None:
        try:
            if not callable(provider_enricher) or market_rows is not None or provider_snapshot_version is not None:
                raise ValueError("provider enrichment conflicts with supplied market snapshot")
            # An integration may gather facts, but may not mutate the inputs or
            # rule configuration used by deterministic report generation.
            enrichment = provider_enricher(copy.deepcopy(parsed), copy.deepcopy(effective_config))
            market_rows, provider_snapshot_version, usage = _provider_result(enrichment)
            write_json(storage_root, task_id, run_id, "provider-usage.json", {
                "schema_version": "provider-usage-0.1",
                "provider_snapshot_version": provider_snapshot_version,
                "usage": usage,
            })
        except Exception:
            reason = {"code": "PROVIDER_ENRICHMENT_FAILED", "message": "Provider enrichment failed or returned an invalid contract; inspect the authorized provider separately", "stage": "provider", "retryable": False}
            _write(root / "failure.json", reason)
            return TaskExecutionResult(task_id, run_id, "failed", "provider", reason)
    try:
        report = build_report(input_path, root, effective_config, market_rows, provider_snapshot_version)
    except (ParseError, ValueError) as exc:
        reason = {"code": "REPORT_GENERATION_FAILED", "message": str(exc), "stage": "report", "retryable": False}
        _write(root / "failure.json", reason)
        return TaskExecutionResult(task_id, run_id, "failed", "report", reason)
    _write(root / "rules-snapshot.json", {
        "schema_version": "rules-snapshot-0.1",
        "rule_version": report["rule_version"],
        "config_version": report["config_version"],
        "provider_snapshot_version": report["provider_snapshot_version"],
        "effective_config": effective_config,
    })
    _write(root / "rank-benchmark.json", {"schema_version": "module02-0.1", "rows": build_rank_benchmark(report["rows"])})
    _write(root / "negative-keywords.json", {"schema_version": "module03-0.1", "write_back": False, **build_negative_keywords(report["rows"], effective_config)})
    _write(root / "optimization-plan.json", {"schema_version": "optimization-plan-0.1", "ai_may_change_action": False, "actions": build_optimization_plan(report["rows"], effective_config)})
    if validated_competitor_profile is not None:
        _write(root / "competitors.json", validated_competitor_profile)
    # Keep the run manifest aligned with every report-0.2 artifact.  The
    # operational fields identify the run; the shared fields make a copied
    # run-meta sufficient to verify lineage without opening the report rows.
    _write(root / "run-meta.json", {
        **shared_traceability(report),
        "task_id": task_id,
        "run_id": run_id,
        "status": "completed",
        "current_stage": "report",
    })
    return TaskExecutionResult(task_id, run_id, "completed", "report", report_path=str(root / "master-table.json"))
