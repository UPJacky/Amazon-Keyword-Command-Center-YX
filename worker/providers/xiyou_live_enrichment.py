"""Explicit get_keyword_info enrichment using the recorded 2026-09-02 contract.

No environment access, discovery, implicit transport, retries or disk cache.
The callable fits task_runner.ProviderEnricher. Share one XiyouCallBudget across
task factories; its lock serializes reservation, transport and cost settlement.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import date
from typing import Any, Mapping

from worker.providers.base import ProviderTransport
from worker.providers.market_merge import MARKET_FIELDS
from worker.providers.orchestrator import CallBudget, ProviderBatchError


CONTRACT_VERSION = "xiyou-get-keyword-info-recorded-20260902-v1"
TOOL_NAME = "get_keyword_info"
COMPETITOR_TOOL_NAME = "get_keyword_asin_analysis"


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _keyword(value: Any) -> str:
    if (not isinstance(value, str) or not value.strip()
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise ValueError("invalid keyword")
    return " ".join(value.split()).casefold()


def _fail(code: str, usage: dict[str, int]) -> None:
    usage["failures"] += 1
    raise ProviderBatchError(code, usage) from None


class XiyouCallBudget:
    """Process-lifetime attempt/credit ceilings, with no unlimited defaults.

    used_credits is conservative consumption: max(reservation, reported cost)
    per attempt. reported_credits counts only known response charges. Unknown
    charges retain the reservation and permanently block further attempts.
    Server overcharging is detected after the response, never hidden/clamped.
    """

    def __init__(self, max_calls: int, max_credits: int):
        if not _integer(max_credits):
            raise ValueError("max_credits must be an explicit non-negative integer")
        self._calls = CallBudget(max_calls)
        self._max_credits = max_credits
        self._used_credits = 0
        self._reported_credits = 0
        self._blocked = False
        self._lock = threading.RLock()

    @property
    def used_calls(self) -> int:
        return self._calls.used

    @property
    def used_credits(self) -> int:
        with self._lock:
            return self._used_credits

    @property
    def blocked(self) -> bool:
        with self._lock:
            return self._blocked

    def snapshot(self) -> dict[str, Any]:
        """Non-sensitive budget receipt; deliberately outside pipeline usage."""
        with self._lock:
            return {"max_calls": self._calls.max_calls, "used_calls": self.used_calls,
                    "max_credits": self._max_credits, "used_credits": self._used_credits,
                    "reported_credits": self._reported_credits, "blocked": self._blocked}

    def _reserve(self, credits: int, usage: dict[str, int]) -> None:
        # Caller holds _lock through settlement; a failed credit check cannot
        # consume the CallBudget, and no other task can race this reservation.
        if self._blocked:
            _fail("CREDIT_ACCOUNTING_BLOCKED", usage)
        if self._used_credits + credits > self._max_credits:
            _fail("CREDIT_BUDGET_EXHAUSTED", usage)
        if not self._calls.reserve():
            _fail("CALL_BUDGET_EXHAUSTED", usage)
        self._used_credits += credits

    def _settle(self, cost: Any, reserved: int, usage: dict[str, int]) -> None:
        if not _integer(cost):
            self._blocked = True
            _fail("INVALID_COST_CREDITS", usage)
        self._reported_credits += cost
        self._used_credits += max(0, cost - reserved)
        if cost > reserved:
            self._blocked = True
            _fail("COST_EXCEEDS_RESERVATION", usage)


class XiyouLiveEnricher:
    """One tools/call per nonempty sample; country and ASIN are never inferred.

    Input: parsed['aggregated_rows'] in parser order. Select the first
    max_keywords unique normalized keywords, while preserving exact input
    spellings in market_rows for market_merge's exact-key join. Unsampled or
    omitted keywords get explicit missing values. ASIN partitions provenance;
    it is NOT sent to this keyword-only tool or used to invent rank data.
    """

    full_report_complete = False

    def __init__(self, *, transport: ProviderTransport, country: str, asin: str,
                 max_keywords: int, budget: XiyouCallBudget,
                 enable_competitors: bool = False):
        if not callable(getattr(transport, "call", None)):
            raise ValueError("transport must provide a single-attempt call method")
        if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("country must be an explicitly supplied uppercase country code")
        if not isinstance(asin, str) or not re.fullmatch(r"[A-Z0-9]{10}", asin):
            raise ValueError("asin must be an explicitly supplied ten-character ASIN")
        if not _integer(max_keywords) or not 1 <= max_keywords <= 10:
            raise ValueError("max_keywords must be an explicit integer from 1 to 10")
        if not isinstance(budget, XiyouCallBudget):
            raise ValueError("budget must be a shared XiyouCallBudget")
        self._transport = transport
        self._country = country
        self._asin = asin
        self._max_keywords = max_keywords
        self._budget = budget
        self._enable_competitors = enable_competitors is True

    def __call__(self, parsed: Mapping[str, Any], effective_config: Mapping[str, Any]) -> dict[str, Any]:
        usage = dict(requested_keywords=0, estimated_calls=0, actual_calls=0,
                     cache_hits=0, retries=0, rate_limited=0, failures=0,
                     duplicates_suppressed=0)
        try:
            if not isinstance(parsed, Mapping) or not isinstance(effective_config, Mapping):
                raise ValueError("invalid input")
            rows = parsed.get("aggregated_rows")
            if not isinstance(rows, list):
                raise ValueError("missing aggregated_rows")
            unique: dict[str, str] = {}
            originals: dict[str, str] = {}
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("invalid row")
                original = row.get("keyword")
                key = _keyword(original)
                originals[original] = key
                unique.setdefault(key, original)
            usage["requested_keywords"] = len(rows)
            usage["duplicates_suppressed"] = len(rows) - len(unique)
        except (TypeError, ValueError):
            _fail("INVALID_KEYWORD_INPUT", usage)

        selected = dict(list(unique.items())[:self._max_keywords])
        usage["estimated_calls"] = int(bool(selected))
        observations: dict[str, dict[str, Any]] = {}
        if selected:
            # Recorded calls cost one credit. Keep one request at <=10 terms;
            # do not infer bulk pricing or silently split into extra calls.
            reserved = 1
            with self._budget._lock:
                self._budget._reserve(reserved, usage)
                usage["actual_calls"] += 1
                try:
                    response = self._transport.call(TOOL_NAME, {
                        "keywords": list(selected.values()), "country": self._country,
                    })
                except Exception as exc:
                    if getattr(exc, "status_code", None) == 429:
                        usage["rate_limited"] += 1
                    self._budget._blocked = True
                    _fail("TRANSPORT_FAILED", usage)
                try:
                    structured = self._envelope(response, usage)
                except ProviderBatchError:
                    self._budget._blocked = True
                    raise
                self._budget._settle(structured.get("cost_credits"), reserved, usage)
                status = structured.get("status")
                if type(status) is not int or status != 200:
                    usage["rate_limited"] += int(type(status) is int and status == 429)
                    _fail("BUSINESS_STATUS_FAILED", usage)
                try:
                    observations = self._observations(structured.get("data"), selected)
                except (TypeError, ValueError):
                    _fail("INVALID_KEYWORD_RESPONSE", usage)

        competitor_profile = None
        if self._enable_competitors and selected:
            competitor_profile = self._fetch_competitor_profile(next(iter(selected.values())), usage)

        market_rows = [self._market_row(original, observations.get(key), key in selected)
                       for original, key in originals.items()]
        # A local content digest, not an assertion about the live server version.
        version_input = {"contract": CONTRACT_VERSION, "country": self._country,
                         "asin": self._asin, "selected": list(selected.values()),
                         "market_rows": market_rows}
        digest = hashlib.sha256(json.dumps(version_input, ensure_ascii=False,
                                         sort_keys=True, allow_nan=False,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
        result = {"market_rows": market_rows,
                  "provider_snapshot_version": "snapshot-xiyou-" + digest, "usage": usage}
        if competitor_profile is not None:
            result["competitor_profile"] = competitor_profile
        return result

    def _fetch_competitor_profile(self, keyword: str, usage: dict[str, int]) -> dict[str, Any] | None:
        """Best-effort keyword-to-ASIN snapshot for the competitor module.

        The keyword analysis endpoint returns product identity and image URLs,
        which are sufficient to persist a comparison evidence set.  Missing or
        malformed provider rows remain a partial module; they never become
        invented competitors and do not abort the already valid ad report.
        """
        reserved = 1
        try:
            with self._budget._lock:
                self._budget._reserve(reserved, usage)
                usage["actual_calls"] += 1
                response = self._transport.call(COMPETITOR_TOOL_NAME, {
                    "keyword": keyword, "country": self._country, "page": 1,
                    "page_size": 5, "sort_field": "traffic", "sort_order": "desc",
                })
                structured = self._envelope(response, usage)
                self._budget._settle(structured.get("cost_credits"), reserved, usage)
                if structured.get("status") != 200:
                    return None
                data = structured.get("data")
                entries = data.get("list") if isinstance(data, Mapping) else None
                if not isinstance(entries, list):
                    return None
                rows = [self._product_row(entry, role="competitor") for entry in entries]
                rows = [row for row in rows if row is not None and row["asin"] != self._asin]
                rows = rows[:3]
                own_entry = next((entry for entry in entries
                                  if isinstance(entry, Mapping) and entry.get("asin") == self._asin), None)
                own = self._product_row(own_entry, role="self") if own_entry is not None else {
                    "asin": self._asin, "image_urls": [], "source": COMPETITOR_TOOL_NAME,
                    "provider_sampled": True,
                }
                if not rows:
                    return None
                return {
                    "self_asin": self._asin, "marketplace": self._country,
                    "core_keywords": [keyword], "competitors": rows,
                    "self_product": own,
                    "snapshot_version": "snapshot-xiyou-competitors-v1",
                }
        except Exception:
            # The market keyword call remains usable even when the optional
            # competitor endpoint has no result or changes schema.
            return None

    @staticmethod
    def _product_row(entry: Any, *, role: str) -> dict[str, Any] | None:
        if not isinstance(entry, Mapping):
            return None
        asin = entry.get("asin")
        info = entry.get("asinInfo")
        if not isinstance(asin, str) or not re.fullmatch(r"[A-Z0-9]{10}", asin):
            return None
        info = info if isinstance(info, Mapping) else {}
        image = info.get("picUrl")
        row = {
            "asin": asin.upper(), "role": role,
            "title": info.get("title"), "main_image_url": image,
            "image_urls": [image] if isinstance(image, str) and image.strip() else [],
            "price": info.get("price"), "currency_code": info.get("currency"),
            "rating": info.get("stars"), "review_count": info.get("ratings"),
            "source": COMPETITOR_TOOL_NAME, "provider_sampled": True,
        }
        return row

    @staticmethod
    def _envelope(response: Any, usage: dict[str, int]) -> Mapping[str, Any]:
        if not isinstance(response, Mapping):
            _fail("INVALID_MCP_RESPONSE", usage)
        status = response.get("status")
        if status is not None:
            if type(status) is int and status == 429:
                usage["rate_limited"] += 1
            if type(status) is not int or status != 200:
                _fail("HTTP_STATUS_FAILED", usage)
        if response.get("jsonrpc") != "2.0" or "error" in response:
            _fail("INVALID_MCP_RESPONSE", usage)
        result = response.get("result")
        if not isinstance(result, Mapping) or "error" in result:
            _fail("INVALID_MCP_RESULT", usage)
        if "isError" in result and result["isError"] is not False:
            _fail("MCP_TOOL_FAILED", usage)
        structured = result.get("structuredContent")
        if not isinstance(structured, Mapping):
            _fail("MISSING_STRUCTURED_CONTENT", usage)
        return structured

    def _observations(self, data: Any, selected: Mapping[str, str]) -> dict[str, dict[str, Any]]:
        if not isinstance(data, Mapping) or not isinstance(data.get("list"), list):
            raise ValueError("missing list")
        entries = data["list"]
        if (not _integer(data.get("total")) or data["total"] != len(entries)
                or len(entries) > len(selected)):
            raise ValueError("invalid total or duplicate results")
        observations = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("invalid entry")
            key = _keyword(entry.get("searchTerm"))
            if key not in selected or key in observations:
                raise ValueError("cross-keyword or duplicate response")
            # These optional identity echoes were not required by the recorded
            # schema; if present they must agree, never override the task.
            if "country" in entry and entry["country"] != self._country:
                raise ValueError("cross-country response")
            if "asin" in entry and entry["asin"] != self._asin:
                raise ValueError("cross-ASIN response")
            difficulty = entry.get("competitiveDifficulty")
            if difficulty is not None and not _integer(difficulty):
                raise ValueError("invalid difficulty")
            aba = entry.get("abaReport")
            observed_aba = None
            if aba is not None:
                if not isinstance(aba, Mapping):
                    raise ValueError("invalid ABA report")
                observed_aba = {}
                for field in ("reportFromDate", "reportToDate"):
                    value = aba.get(field)
                    if value is not None:
                        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                            raise ValueError("invalid report date")
                        date.fromisoformat(value)
                    observed_aba[field] = value
                start, end = observed_aba["reportFromDate"], observed_aba["reportToDate"]
                if start is not None and end is not None and start > end:
                    raise ValueError("reversed report period")
                for field in ("weeklySearchVolume", "searchFrequencyRank"):
                    value = aba.get(field)
                    if value is not None and (not _integer(value) or (field == "searchFrequencyRank" and value == 0)):
                        raise ValueError("invalid ABA metric")
                    observed_aba[field] = value
            observations[key] = {"competitiveDifficulty": difficulty, "abaReport": observed_aba}
        return observations

    def _market_row(self, keyword: str, observation: dict[str, Any] | None, sampled: bool) -> dict[str, Any]:
        row = {field: None for field in MARKET_FIELDS}
        if observation is not None:
            # Direct integer identity only: no invented 0..100 scale or labels.
            row["competitive_difficulty"] = observation["competitiveDifficulty"]
            aba = observation.get("abaReport")
            if aba is not None:
                row.update(
                    weekly_search_volume=aba["weeklySearchVolume"],
                    aba_search_frequency_rank=aba["searchFrequencyRank"],
                    aba_report_from_date=aba["reportFromDate"],
                    aba_report_to_date=aba["reportToDate"],
                )
        row.update(keyword=keyword, asin=self._asin, country=self._country,
                   full_report_complete=False,
                   provider_sampled=sampled,
                   provider_observations=observation,
                   missing_fields=sorted(field for field in MARKET_FIELDS if row[field] is None))
        return row
