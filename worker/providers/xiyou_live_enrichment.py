"""Explicit get_keyword_info enrichment using the recorded 2026-09-02 contract.

No environment access, discovery or implicit transport is performed here. An
explicit ProviderCache may be injected by the production composition root; it
is keyed by the complete non-secret request identity and only successful
normalized results are cached. Share one XiyouCallBudget across task
factories; its lock serializes reservation, transport and cost settlement.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import date
from typing import Any, Iterable, Mapping

from worker.providers.base import ProviderTransport
from worker.providers.market_merge import MARKET_FIELDS
from worker.providers.orchestrator import CallBudget, ProviderBatchError
from worker.providers.cache import ProviderCache
from worker.competitors.text_evidence import build_text_evidence_matrix
from worker.diagnostics.buyer_checklist import build_buyer_checklist


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

    # This class is constructed only around an explicitly supplied live MCP
    # transport by the production worker.  The production runtime uses this
    # marker to distinguish verified live-provider provenance from injected
    # fixtures; the marker is deliberately not inferred from returned data.
    real_provider_verified = True
    full_report_complete = False

    def __init__(self, *, transport: ProviderTransport, country: str, asin: str,
                 max_keywords: int, budget: XiyouCallBudget,
                 enable_competitors: bool = False, catalog_adapter: Any = None,
                 primary_core_keyword: str | None = None,
                 core_keywords: Iterable[str] = (),
                 competitor_asins: Iterable[str] = (),
                 cache: ProviderCache | None = None,
                 cache_namespace: str = "default",
                 feature_review_version: str | None = None,
                 checklist_version: str | None = None,
                 confirmation_version: str | None = None):
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
        if cache is not None and not isinstance(cache, ProviderCache):
            raise ValueError("cache must be a ProviderCache")
        if not isinstance(cache_namespace, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", cache_namespace):
            raise ValueError("cache_namespace must be a non-secret identifier")
        self._transport = transport
        self._country = country
        self._asin = asin
        self._max_keywords = max_keywords
        self._budget = budget
        self._cache = cache
        self._cache_namespace = cache_namespace
        self._feature_review_version = feature_review_version.strip() if isinstance(feature_review_version, str) and feature_review_version.strip() else None
        self._checklist_version = checklist_version.strip() if isinstance(checklist_version, str) and checklist_version.strip() else None
        self._confirmation_version = confirmation_version.strip() if isinstance(confirmation_version, str) and confirmation_version.strip() else None
        self._enable_competitors = enable_competitors is True
        if catalog_adapter is not None and not callable(getattr(catalog_adapter, "enrich_profile", None)):
            raise ValueError("catalog_adapter must provide enrich_profile")
        self._catalog_adapter = catalog_adapter
        self._primary_core_keyword = primary_core_keyword.strip() if isinstance(primary_core_keyword, str) and primary_core_keyword.strip() else None
        self._core_keywords = self._normalize_requested_keywords(core_keywords)
        self._requested_competitor_asins = self._normalize_requested_asins(competitor_asins, asin)

    @staticmethod
    def _normalize_requested_keywords(values: Iterable[str]) -> list[str]:
        if values is None:
            return []
        if isinstance(values, (str, bytes)):
            values = [values]
        result = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("core_keywords must contain nonempty strings")
            result.append(" ".join(value.split()))
        if len(result) > 200:
            raise ValueError("too many core_keywords")
        return list(dict.fromkeys(result))

    @staticmethod
    def _normalize_requested_asins(values: Iterable[str], self_asin: str) -> list[str]:
        if values is None:
            return []
        if isinstance(values, (str, bytes)):
            values = [values]
        result = []
        for value in values:
            if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]{10}", value, re.I):
                raise ValueError("competitor_asins must contain ten-character ASINs")
            result.append(value.upper())
        if len(result) > 5 or len(set(result)) != len(result) or self_asin.upper() in result:
            raise ValueError("invalid competitor_asins")
        return result

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

        # User-confirmed intent gets first position in the bounded request.
        # If the primary term is not present in the ad report, it is still
        # queried explicitly; the response will remain an unjoined market
        # observation instead of being fabricated into an ad row.
        requested = []
        if self._primary_core_keyword:
            requested.append(self._primary_core_keyword)
        requested.extend(self._core_keywords)
        selected_candidates: dict[str, str] = {}
        for value in requested:
            selected_candidates.setdefault(_keyword(value), value)
        selected_candidates.update({key: value for key, value in unique.items()
                                    if key not in selected_candidates})
        selected = dict(list(selected_candidates.items())[:self._max_keywords])
        usage["estimated_calls"] = int(bool(selected))
        cache_key = self._cache_key(selected)
        if self._cache is not None:
            try:
                cached = self._cache.get(cache_key)
            except (OSError, ValueError, json.JSONDecodeError):
                cached = None
            if isinstance(cached, Mapping) and cached.get("provider") == "xiyou-live-enricher":
                cached_result = cached.get("data")
                if isinstance(cached_result, Mapping) and isinstance(cached_result.get("market_rows"), list):
                    result = json.loads(json.dumps(cached_result, ensure_ascii=False, allow_nan=False))
                    cached_usage = dict(result.get("usage") or {})
                    cached_usage.update({
                        "requested_keywords": usage["requested_keywords"],
                        "duplicates_suppressed": usage["duplicates_suppressed"],
                        "estimated_calls": 0,
                        "actual_calls": 0,
                        "cache_hits": 1,
                        "retries": 0,
                        "rate_limited": 0,
                        "failures": 0,
                    })
                    result["usage"] = cached_usage
                    return result
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
            if competitor_profile is not None and self._catalog_adapter is not None:
                try:
                    competitor_profile = self._catalog_adapter.enrich_profile(competitor_profile)
                except Exception:
                    # The keyword snapshot remains valid but the product
                    # profile must retain its partial state.
                    competitor_profile["sorftime_enrichment_failed"] = True

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
            category_features = getattr(self._catalog_adapter, "last_category_features", None)
            if isinstance(category_features, Mapping):
                result["category_features"] = dict(category_features)
                evidence = self._build_business_evidence(category_features, competitor_profile)
                if evidence["buyer_checklist"] is not None:
                    result["buyer_checklist"] = evidence["buyer_checklist"]
                if evidence["text_evidence"] is not None:
                    result["text_evidence"] = evidence["text_evidence"]
        if self._cache is not None:
            try:
                self._cache.set(cache_key, provider="xiyou-live-enricher",
                                snapshot_version=result["provider_snapshot_version"], data=result)
            except (OSError, ValueError, TypeError):
                # Cache failure must not convert an already successful remote
                # response into a failed task. The usage receipt stays true.
                pass
        return result

    def _build_business_evidence(self, category_features: Mapping[str, Any],
                                 competitor_profile: Mapping[str, Any]) -> dict[str, Any]:
        features = category_features.get("features")
        if not isinstance(features, list) or not features:
            return {"buyer_checklist": None, "text_evidence": None}
        candidates = []
        for index, feature in enumerate(features, start=1):
            if not isinstance(feature, Mapping):
                continue
            feature_id = str(feature.get("feature_id") or "").strip()
            name = str(feature.get("name") or "").strip()
            if not feature_id or not name:
                continue
            candidates.append({
                "element_id": feature_id,
                "name": name,
                "english_name": feature.get("english_name"),
                "why_buyer_cares": feature.get("feature_description"),
                "source_refs": feature.get("source_refs") or category_features.get("source_refs") or [],
                "priority": index,
            })
        version = self._checklist_version or self._confirmation_version
        checklist = build_buyer_checklist(candidates=candidates, confirmation_version=version)
        products = []
        own = competitor_profile.get("self_product")
        if isinstance(own, Mapping):
            products.append(dict(own))
        products.extend(dict(row) for row in competitor_profile.get("competitors", []) if isinstance(row, Mapping))
        text_evidence = None
        ids = [item["element_id"] for item in candidates]
        if products and ids:
            text_evidence = build_text_evidence_matrix(
                features, products,
                confirmed_feature_ids=ids,
                confirmation_version=self._feature_review_version or self._confirmation_version or "unconfirmed",
            )
            if version is None:
                text_evidence["status"] = "draft"
                text_evidence["reason"] = "confirmation_required"
        return {"buyer_checklist": checklist, "text_evidence": text_evidence}

    def _cache_key(self, selected: Mapping[str, str]) -> str:
        """Hash the complete request identity without storing credentials."""
        payload = {
            "namespace": self._cache_namespace,
            "contract": CONTRACT_VERSION,
            "country": self._country,
            "asin": self._asin,
            "max_keywords": self._max_keywords,
            "enable_competitors": self._enable_competitors,
            "catalog_enabled": self._catalog_adapter is not None,
            "primary_core_keyword": self._primary_core_keyword,
            "core_keywords": self._core_keywords,
            "competitor_asins": self._requested_competitor_asins,
            "selected": list(selected.items()),
        }
        return "xiyou-" + hashlib.sha256(json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()

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
                if self._requested_competitor_asins:
                    by_asin = {row["asin"]: row for row in rows}
                    rows = [by_asin[asin] for asin in self._requested_competitor_asins if asin in by_asin]
                else:
                    rows = rows[:3]
                own_entry = next((entry for entry in entries
                                  if isinstance(entry, Mapping) and entry.get("asin") == self._asin), None)
                own = self._product_row(own_entry, role="self") if own_entry is not None else {
                    "asin": self._asin, "image_urls": [], "source": COMPETITOR_TOOL_NAME,
                    "provider_sampled": True,
                }
                if not rows:
                    return None
                profile = {
                    "self_asin": self._asin, "marketplace": self._country,
                    "core_keywords": [self._primary_core_keyword or keyword],
                    "primary_core_keyword": self._primary_core_keyword or keyword,
                    "competitors": rows,
                    "self_product": own,
                    "snapshot_version": "snapshot-xiyou-competitors-v1",
                }
                if self._requested_competitor_asins:
                    found = {row["asin"] for row in rows}
                    profile["requested_competitor_asins"] = list(self._requested_competitor_asins)
                    profile["missing_competitor_asins"] = [asin for asin in self._requested_competitor_asins if asin not in found]
                return profile
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
                top_asins = aba.get("topAsins")
                if top_asins is not None and not isinstance(top_asins, list):
                    raise ValueError("invalid ABA top ASINs")
                # The recorded contract guarantees an array but not a stable
                # per-item schema. Project only an explicit valid `asin`; do
                # not invent rank/share from opaque provider objects.
                benchmark_asins = []
                for item in top_asins or []:
                    if not isinstance(item, Mapping):
                        continue
                    value = item.get("asin")
                    if isinstance(value, str) and re.fullmatch(r"[A-Z0-9]{10}", value, re.I):
                        benchmark_asins.append(value.upper())
                observed_aba["topAsins"] = top_asins
                observed_aba["benchmark_asins"] = list(dict.fromkeys(benchmark_asins))[:3]
            observations[key] = {"competitiveDifficulty": difficulty, "abaReport": observed_aba}
            if observed_aba is not None:
                observations[key]["benchmark_asins"] = observed_aba.get("benchmark_asins", [])
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
                benchmark_asins = aba.get("benchmark_asins") or []
                if benchmark_asins:
                    row["benchmark_asins"] = benchmark_asins
                    row["top3_asins"] = benchmark_asins
        row.update(keyword=keyword, asin=self._asin, country=self._country,
                   full_report_complete=False,
                   provider_sampled=sampled,
                   provider_observations=observation,
                   missing_fields=sorted(field for field in MARKET_FIELDS if row[field] is None))
        return row
