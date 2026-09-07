"""Deterministic Amazon search-term report parser.

The parser aggregates raw count/currency fields first and derives rates only
after aggregation. It deliberately keeps missing values distinct from zero.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import uuid
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from worker.security.path_guard import contains_link_or_reparse, is_link_or_reparse

PARSER_VERSION = "ad-report-parser-0.2.0"
MONEY_TOLERANCE = Decimal("0.01")


class ParseError(ValueError):
    """Raised when the input cannot be safely interpreted."""


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.lower())


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_missing(value: Any) -> bool:
    return _text(value).casefold() in {"", "-", "—", "–", "n/a", "null", "none"}


def _decimal(value: Any, *, field: str) -> Decimal:
    if _is_missing(value):
        return Decimal("0")
    if isinstance(value, bool):
        raise ParseError(f"{field}: boolean is not a valid number: {value!r}")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    cleaned = _text(value).replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    cleaned = cleaned.replace("￥", "").replace("¥", "").replace(" ", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"{field}: invalid numeric value {value!r}") from exc
    if not parsed.is_finite():
        raise ParseError(f"{field}: non-finite numeric value is not allowed: {value!r}")
    return parsed


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _rate(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


ALIASES: Mapping[str, tuple[str, ...]] = {
    "keyword": ("客户搜索词", "搜索词", "customersearchterm", "searchterm", "keyword", "query"),
    "impressions": ("展示量", "曝光量", "展示", "impressions", "impression"),
    "clicks": ("点击量", "点击", "clicks", "click"),
    "spend": ("花费", "广告花费", "spend", "cost"),
    "sales": ("7天总销售额", "总销售额", "销售额", "sales", "salesamount", "revenue"),
    "orders": ("7天总订单数", "总订单数", "订单数", "订单", "orders", "order"),
    "currency": ("货币", "币种", "currency", "currencycode"),
    # These fields are optional.  They must be carried through aggregation
    # when present so later diagnostics can distinguish an ad entity from a
    # search-term-only aggregate.  They never become required input fields.
    "campaign_id": ("广告活动id", "广告活动id", "campaignid", "campaign_id"),
    "campaign_name": ("广告活动名称", "广告活动", "campaignname", "campaign"),
    "ad_group_id": ("广告组id", "adgroupid", "ad_group_id"),
    "ad_group_name": ("广告组名称", "广告组", "adgroupname", "ad_group"),
    "target_id": ("投放id", "targetid", "target_id"),
    "target": ("投放", "投放目标", "targeting", "target"),
    "match_type": ("匹配类型", "matchtype", "match_type", "match"),
    "targeting_type": ("投放类型", "targetingtype", "targeting_type"),
    "ad_type": ("广告类型", "adtype", "ad_type"),
}

ENTITY_FIELDS = (
    "campaign_id", "campaign_name", "ad_group_id", "ad_group_name",
    "target_id", "target", "match_type", "targeting_type", "ad_type",
)


def _find_column(headers: Sequence[Any], field: str) -> int | None:
    normalized = [_norm(value) for value in headers]
    aliases = {_norm(alias) for alias in ALIASES[field]}
    exact = [i for i, value in enumerate(normalized) if value in aliases]
    if exact:
        return exact[0]
    contains = [i for i, value in enumerate(normalized) if any(alias in value for alias in aliases if alias)]
    return contains[0] if contains else None


def _select_header(rows: Sequence[Sequence[Any]]) -> tuple[int, list[Any], dict[str, int]]:
    for row_index, row in enumerate(rows[:30]):
        columns = {field: _find_column(row, field) for field in ("keyword", "impressions", "clicks", "spend", "sales", "orders")}
        if columns["keyword"] is not None and columns["impressions"] is not None and columns["clicks"] is not None:
            missing = [field for field in ("spend", "sales", "orders") if columns[field] is None]
            if missing:
                raise ParseError(f"header row {row_index + 1}: missing required columns: {', '.join(missing)}")
            currency = _find_column(row, "currency")
            if currency is not None:
                columns["currency"] = currency
            for field in ENTITY_FIELDS:
                optional = _find_column(row, field)
                if optional is not None:
                    columns[field] = optional
            return row_index, list(row), columns
    raise ParseError("could not find a header containing keyword, impressions and clicks columns")


def _read_rows(path: Path) -> list[list[Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiters = "\t" if suffix == ".tsv" else ","
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    return [list(row) for row in csv.reader(handle, delimiter=delimiters)]
            except UnicodeDecodeError:
                continue
        raise ParseError(f"unable to decode {path.name}")
    if suffix == ".xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ParseError("XLSX support requires openpyxl in the configured runtime") from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        if not workbook.sheetnames:
            raise ParseError("workbook contains no sheets")
        return [list(row) for row in workbook[workbook.sheetnames[0]].iter_rows(values_only=True)]
    raise ParseError(f"unsupported input format: {path.suffix}; expected .xlsx, .csv or .tsv")


def _canonical_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(list(rows), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _contains_symlink(path: Path) -> bool:
    return contains_link_or_reparse(path)


def _write_json_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists() or is_link_or_reparse(path):
        raise ParseError("output artifact already exists; historical artifacts are immutable")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ParseError("output artifact already exists; historical artifacts are immutable") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def _parse_once(path: Path) -> dict[str, Any]:
    rows = _read_rows(path)
    header_index, headers, columns = _select_header(rows)
    currency_index = columns.get("currency")
    currencies: set[str] = set()
    metric_fields = ("impressions", "clicks", "spend", "sales", "orders")
    aggregates: dict[str, dict[str, Decimal]] = defaultdict(lambda: {field: Decimal("0") for field in metric_fields})
    missing_by_keyword: dict[str, set[str]] = defaultdict(set)
    valid_rows = 0
    raw_totals = {field: Decimal("0") for field in ("impressions", "clicks", "spend", "sales", "orders")}
    raw_keywords: list[str] = []
    entity_contexts: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows[header_index + 1 :]:
        if not row or all(_is_missing(cell) for cell in row):
            continue
        keyword = _text(row[columns["keyword"]]) if columns["keyword"] < len(row) else ""
        if _is_missing(keyword):
            continue
        values: dict[str, Decimal] = {}
        row_missing: set[str] = set()
        for field in metric_fields:
            index = columns[field]
            raw_value = row[index] if index < len(row) else None
            if _is_missing(raw_value):
                row_missing.add(field)
            values[field] = _decimal(row[index] if index < len(row) else None, field=field)
        if currency_index is not None and currency_index < len(row) and not _is_missing(row[currency_index]):
            currencies.add(_text(row[currency_index]).upper())
        entity = {
            field: _text(row[index])
            for field in ENTITY_FIELDS
            if (index := columns.get(field)) is not None
            and index < len(row)
            and not _is_missing(row[index])
        }
        if entity:
            signature = json.dumps(entity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if not any(json.dumps(existing, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == signature
                       for existing in entity_contexts[keyword]):
                entity_contexts[keyword].append(entity)
        valid_rows += 1
        raw_keywords.append(keyword)
        missing_by_keyword[keyword].update(row_missing)
        for field, value in values.items():
            raw_totals[field] += value
            aggregates[keyword][field] += value

    if len(currencies) > 1:
        raise ParseError(f"multiple currencies found in one task: {sorted(currencies)}")
    currency_code = next(iter(currencies), None)
    aggregate_rows: list[dict[str, Any]] = []
    for keyword in sorted(
        aggregates,
        key=lambda value: (
            unicodedata.normalize("NFC", value).casefold(),
            unicodedata.normalize("NFC", value),
            value,
        ),
    ):
        values = aggregates[keyword]
        missing_fields = missing_by_keyword.get(keyword, set())
        known = {field: field not in missing_fields for field in metric_fields}
        impressions = _number(values["impressions"]) if known["impressions"] else None
        clicks = _number(values["clicks"]) if known["clicks"] else None
        spend = _number(values["spend"]) if known["spend"] else None
        sales = _number(values["sales"]) if known["sales"] else None
        orders = _number(values["orders"]) if known["orders"] else None
        contexts = sorted(
            entity_contexts.get(keyword, []),
            key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        aggregate_rows.append({
            "keyword": keyword,
            "impressions": impressions,
            "clicks": clicks,
            "spend": spend,
            "sales": sales,
            "orders": orders,
            "ctr": _rate(values["clicks"], values["impressions"]) if all(known[field] for field in ("clicks", "impressions")) else None,
            "cpc": _rate(values["spend"], values["clicks"]) if all(known[field] for field in ("spend", "clicks")) else None,
            "cvr": _rate(values["orders"], values["clicks"]) if all(known[field] for field in ("orders", "clicks")) else None,
            "acos": _rate(values["spend"], values["sales"]) if all(known[field] for field in ("spend", "sales")) else None,
            "roas": _rate(values["sales"], values["spend"]) if all(known[field] for field in ("sales", "spend")) else None,
            # Empty is intentional: it means the source did not provide an
            # ad-entity column, not that a fabricated entity was inferred.
            "ad_entities": contexts,
        })
        if missing_fields:
            aggregate_rows[-1]["missing_fields"] = sorted(missing_fields)

    aggregate_totals = {field: sum((values[field] for values in aggregates.values()), Decimal("0")) for field in raw_totals}
    differences = {field: raw_totals[field] - aggregate_totals[field] for field in raw_totals}
    passed = (
        differences["impressions"] == 0
        and differences["clicks"] == 0
        and differences["orders"] == 0
        and abs(differences["spend"]) <= MONEY_TOLERANCE
        and abs(differences["sales"]) <= MONEY_TOLERANCE
    )
    keyword_counts = defaultdict(int)
    for keyword in raw_keywords:
        keyword_counts[keyword] += 1
    reconciliation = {
        "schema_version": "reconciliation-0.1",
        "parser_version": PARSER_VERSION,
        "raw_row_count": len(rows) - header_index - 1,
        "valid_row_count": valid_rows,
        "unique_keyword_count": len(aggregate_rows),
        "repeated_keyword_count": sum(1 for count in keyword_counts.values() if count > 1),
        "duplicate_row_count": len(raw_keywords) - len(set(raw_keywords)),
        "currency_code": currency_code,
        "header_mapping": {
            field: {"index": columns[field], "label": str(headers[columns[field]])}
            for field in metric_fields + ("keyword",)
        },
        "entity_header_mapping": {
            field: {"index": columns[field], "label": str(headers[columns[field]])}
            for field in ENTITY_FIELDS if field in columns
        },
        "raw_totals": {field: str(raw_totals[field]) for field in raw_totals},
        "aggregated_totals": {field: str(aggregate_totals[field]) for field in aggregate_totals},
        "differences": {field: str(differences[field]) for field in differences},
        "tolerances": {"integer_metrics": "0", "money_metrics": str(MONEY_TOLERANCE)},
        "ratio_recalculation": {"source": "aggregated_raw_metrics", "checked_rows": len(aggregate_rows)},
        "repeat_parse_consistent": None,
        "passed": passed,
    }
    return {"aggregate_rows": aggregate_rows, "reconciliation": reconciliation}


def parse_report(input_path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Parse a report and optionally write deterministic JSON artifacts."""
    path = Path(input_path)
    current = path
    while current != current.parent:
        if is_link_or_reparse(current):
            raise ParseError("input path must not contain a symbolic link")
        current = current.parent
    if not path.is_file():
        raise ParseError(f"input file does not exist: {path}")
    first = _parse_once(path)
    second = _parse_once(path)
    consistent = _canonical_rows(first["aggregate_rows"]) == _canonical_rows(second["aggregate_rows"])
    first["reconciliation"]["repeat_parse_consistent"] = consistent
    first["reconciliation"]["passed"] = bool(first["reconciliation"]["passed"] and consistent)
    result = {
        "schema_version": "ad-aggregated-0.1",
        "parser_version": PARSER_VERSION,
        "input_file": path.name,
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "currency_code": first["reconciliation"]["currency_code"],
        "aggregated_rows": first["aggregate_rows"],
        "reconciliation": first["reconciliation"],
    }
    if output_dir is not None:
        raw_destination = Path(output_dir)
        if _contains_symlink(raw_destination):
            raise ParseError("output path must not contain a symbolic link")
        destination = raw_destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        if _contains_symlink(destination):
            raise ParseError("output path must not contain a symbolic link")
        _write_json_immutable(destination / "ad-aggregated.json", result)
        _write_json_immutable(destination / "reconciliation.json", first["reconciliation"])
    return result
