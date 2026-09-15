"""Adapter for the native Sorftime MCP product and category responses.

Sorftime returns JSON-RPC tool results as a content text block. This module
parses only the confirmed product_detail and similar_product_feature shapes,
keeps missing values explicit, and never exposes the query credential.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
import math
import re
import threading
import time
from copy import deepcopy
from typing import Any, Mapping

from worker.competitors.category_features import normalize_category_features
from worker.competitors.profile import COMPARISON_FIELDS
from worker.providers.base import RetryPolicy, retry_delay
from worker.providers.cache import ProviderCache


ASIN = re.compile(r"^[A-Z0-9]{10}$")
_PRODUCT_TOOL = "product_detail"
_FEATURE_TOOL = "similar_product_feature"
_ADAPTER_VERSION = "sorftime-catalog-v2"


def _digest(value: Any) -> str | None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def _content_json(response: Any) -> Mapping[str, Any]:
    if not isinstance(response, Mapping) or not isinstance(response.get("content"), list):
        raise ValueError("Sorftime response content is missing")
    if response.get("isError") is True:
        raise ValueError("Sorftime response reports an error")
    texts = [item.get("text") for item in response["content"]
             if isinstance(item, Mapping) and item.get("type") == "text"
             and isinstance(item.get("text"), str)]
    if len(texts) != 1:
        raise ValueError("Sorftime response must contain one JSON text block")
    try:
        payload = json.loads(texts[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("Sorftime response text is not JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), Mapping):
        raise ValueError("Sorftime response data is missing")
    code = payload.get("code")
    if isinstance(code, (int, float)) and not isinstance(code, bool) and code >= 400:
        raise ValueError("Sorftime business response reports an error")
    status = str(payload.get("status") or "").strip().casefold()
    if status in {"error", "failed", "failure"}:
        raise ValueError("Sorftime business response reports an error")
    return payload


def _images(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            output.append(item.strip())
        elif isinstance(item, Mapping):
            for key in ("url", "image_url", "imageUrl", "src"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    output.append(candidate.strip())
                    break
    return output


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    """Read only explicit provider aliases; never derive a metric from rank."""
    for key in keys:
        if key in data and data[key] not in (None, "", []):
            return data[key]
    return None


def normalize_product_detail(response: Any, *, asin: str, marketplace: str, sampled_at: str | None = None) -> dict[str, Any]:
    if not isinstance(asin, str) or not ASIN.fullmatch(asin.upper()):
        raise ValueError("asin must be a ten-character ASIN")
    if not isinstance(marketplace, str) or not re.fullmatch(r"[A-Z]{2}", marketplace.upper()):
        raise ValueError("marketplace must be an uppercase country code")
    payload = _content_json(response)
    data = payload["data"]
    returned = data.get("asin")
    if returned is not None and (not isinstance(returned, str) or returned.upper() != asin.upper()):
        raise ValueError("Sorftime returned a different ASIN")
    images = _images(_first(data, "images", "image_urls", "imageUrls", "photos", "photo", "product_images"))
    if not images:
        images = _images(_first(data, "main_image", "mainImage", "main_image_url", "mainImageUrl", "image", "picUrl"))
    variations = _first(data, "variations", "variation_list", "variationList")
    variation_count = _first(data, "variation_count", "variations_count", "variationCount")
    if variation_count is None and isinstance(variations, list):
        variation_count = len(variations)
    currency = _first(data, "currency_code", "currencyCode", "currency")
    bullet_points = _first(data, "bullet_points", "bullets", "feature_bullets")
    bullet_points = [item.strip() for item in bullet_points if isinstance(item, str) and item.strip()] if isinstance(bullet_points, list) else []
    attributes = _first(data, "attributes", "product_attributes", "productAttributes")
    description = _first(data, "description", "product_description", "productDescription")
    row = {
        "asin": asin.upper(),
        "role": "provider",
        "brand": _first(data, "brand", "brand_name", "brandName"),
        "title": _first(data, "title", "product_title", "productTitle", "name"),
        "main_image_url": images[0] if images else None,
        "image_urls": images,
        "price": _first(data, "price", "sale_price", "selling_price", "sellingPrice"),
        "currency_code": currency or ("USD" if marketplace.upper() == "US" else None),
        "rating": _first(data, "star_rating", "stars", "rating"),
        "review_count": _first(data, "review_count", "ratings", "reviews", "rating_count"),
        "monthly_sales": _first(data, "monthly_sales_volume", "monthly_sales", "monthlySales", "sales"),
        "category": _first(data, "category", "subcategory", "top_category", "category_name", "categoryName"),
        "bsr": _first(data, "bsr", "BSR", "sales_rank", "salesRank", "category_rank", "categoryRank"),
        "variation_count": variation_count,
        "variations": variations if isinstance(variations, list) else [],
        "bullet_points": bullet_points,
        "attributes": deepcopy(attributes) if isinstance(attributes, Mapping) else {},
        "description": description if isinstance(description, str) and description.strip() else None,
        "source": _PRODUCT_TOOL,
        "provider_sampled": True,
        "sampled_at": sampled_at,
        "source_refs": ["sorftime:product_detail"],
        "gallery": [{"source_image_id": "sorftime-" + hashlib.sha256(f"{marketplace.upper()}:{asin.upper()}:{url}".encode()).hexdigest()[:24],
                     "url": url, "source": "sorftime:product_detail", "sampled_at": sampled_at}
                    for url in dict.fromkeys(images)],
    }
    missing = [field for field in ("brand", "title", "main_image_url", "price", "rating", "review_count", "monthly_sales", "category", "bsr", "variation_count")
               if row.get(field) in (None, "", [])]
    row["missing_fields"] = missing
    return row


def normalize_category_feature_response(response: Any, *, source: str = "sorftime:similar_product_feature") -> dict[str, Any]:
    payload = _content_json(response)
    data = dict(payload["data"])
    normalized = normalize_category_features(data)
    normalized["source"] = source
    normalized["source_refs"] = [source]
    return normalized


class SorftimeCatalogAdapter:
    """Fetch Sorftime facts with a shared ceiling, disk cache and bounded retry."""

    def __init__(self, *, transport: Any, marketplace: str, max_calls: int = 5, budget: Any = None,
                 cache: ProviderCache | None = None, cache_namespace: str = "default",
                 retry_policy: RetryPolicy | None = None,
                 sleep_fn: Any = time.sleep, preflight_whole_task: bool = False):
        if not callable(getattr(transport, "call", None)):
            raise ValueError("transport must provide call")
        if not isinstance(marketplace, str) or not re.fullmatch(r"[A-Z]{2}", marketplace):
            raise ValueError("marketplace must be an uppercase country code")
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        if cache is not None and not isinstance(cache, ProviderCache):
            raise ValueError("cache must be a ProviderCache")
        if not isinstance(cache_namespace, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", cache_namespace):
            raise ValueError("cache_namespace must be a non-secret identifier")
        if not callable(sleep_fn):
            raise ValueError("sleep_fn must be callable")
        if type(preflight_whole_task) is not bool:
            raise ValueError("preflight_whole_task must be a boolean")
        self.transport = transport
        self.marketplace = marketplace
        self.max_calls = max_calls
        self.budget = budget or _LocalBudget(max_calls)
        self.cache = cache
        self.cache_namespace = cache_namespace
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep_fn = sleep_fn
        self.preflight_whole_task = preflight_whole_task
        self.actual_calls = 0
        self.cache_hits = 0
        self.retries = 0
        self.rate_limited = 0
        self.failures = 0
        self.call_receipts: list[dict[str, Any]] = []
        self.last_category_features: dict[str, Any] | None = None

    def _call(self, tool: str, arguments: dict[str, Any]) -> Mapping[str, Any]:
        attempts = self.retry_policy.max_retries + 1
        for attempt in range(attempts):
            if not self.budget.reserve():
                raise RuntimeError("Sorftime call budget exhausted")
            self.actual_calls += 1
            request_sha256 = _digest(arguments)
            try:
                response = self.transport.call(tool, arguments)
            except Exception as exc:
                status = getattr(self.transport, "last_status", None)
                if status is None:
                    status = getattr(exc, "status_code", None)
                self.call_receipts.append({"provider": "sorftime", "adapter_version": _ADAPTER_VERSION,
                    "tool": tool, "attempt": attempt + 1, "request_sha256": request_sha256,
                    "response_sha256": None, "status": status, "outcome": "transport_error"})
                if status == 429:
                    self.rate_limited += 1
                if status in self.retry_policy.retryable_statuses and attempt < attempts - 1:
                    self.retries += 1
                    fallback = self.retry_policy.backoff_seconds[min(attempt, len(self.retry_policy.backoff_seconds) - 1)] if self.retry_policy.backoff_seconds else 0
                    self.sleep_fn(retry_delay(self.transport, fallback))
                    continue
                self.failures += 1
                raise
            status = response.get("status") if isinstance(response, Mapping) else None
            self.call_receipts.append({"provider": "sorftime", "adapter_version": _ADAPTER_VERSION,
                "tool": tool, "attempt": attempt + 1, "request_sha256": request_sha256,
                "response_sha256": _digest(response), "status": status,
                "outcome": "response" if status not in self.retry_policy.retryable_statuses else "retryable_response"})
            if status in self.retry_policy.retryable_statuses:
                if status == 429:
                    self.rate_limited += 1
                if attempt < attempts - 1:
                    self.retries += 1
                    fallback = self.retry_policy.backoff_seconds[min(attempt, len(self.retry_policy.backoff_seconds) - 1)] if self.retry_policy.backoff_seconds else 0
                    self.sleep_fn(retry_delay(self.transport, fallback))
                    continue
                self.failures += 1
            return response
        raise RuntimeError("Sorftime request failed")

    def _cache_key(self, tool: str, arguments: Mapping[str, Any]) -> str:
        payload = {"provider": "sorftime", "adapter_version": _ADAPTER_VERSION,
                   "namespace": self.cache_namespace, "marketplace": self.marketplace,
                   "tool": tool, "arguments": dict(arguments)}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        return "sorftime-" + digest

    def _cache_lookup(self, key: str) -> dict[str, Any] | None:
        if self.cache is None:
            return None
        try:
            entry = self.cache.get(key)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if (not isinstance(entry, Mapping) or entry.get("provider") != "sorftime"
                or entry.get("cache_key") != key or entry.get("snapshot_version") != _ADAPTER_VERSION
                or not isinstance(entry.get("data"), Mapping)):
            return None
        return deepcopy(dict(entry["data"]))

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        cached = self._cache_lookup(key)
        if cached is not None:
            self.cache_hits += 1
        return cached

    def _cache_has_product(self, asin: str) -> bool:
        arguments = {"asin": asin.upper(), "amz_site": self.marketplace}
        cached = self._cache_lookup(self._cache_key(_PRODUCT_TOOL, arguments))
        return cached is not None and cached.get("asin") == asin.upper()

    def _cache_has_category_features(self, product_name: str) -> bool:
        arguments = {"product_name": product_name.strip(), "amz_site": self.marketplace}
        cached = self._cache_lookup(self._cache_key(_FEATURE_TOOL, arguments))
        return cached is not None and isinstance(cached.get("features"), list)

    def _cache_set(self, key: str, value: Mapping[str, Any]) -> None:
        if self.cache is None:
            return
        try:
            self.cache.set(key, provider="sorftime", snapshot_version=_ADAPTER_VERSION,
                           data=deepcopy(dict(value)))
        except (OSError, ValueError, TypeError):
            # A successful provider response remains valid if the optional
            # local cache cannot be published.
            pass

    def fetch_product(self, asin: str) -> dict[str, Any]:
        if not isinstance(asin, str) or not ASIN.fullmatch(asin.upper()):
            raise ValueError("asin must be a ten-character ASIN")
        arguments = {"asin": asin.upper(), "amz_site": self.marketplace}
        cached = self._cache_get(self._cache_key(_PRODUCT_TOOL, arguments))
        if cached is not None and cached.get("asin") == asin.upper():
            return cached
        row = normalize_product_detail(self._call(_PRODUCT_TOOL, arguments), asin=asin, marketplace=self.marketplace, sampled_at=datetime.now(timezone.utc).isoformat())
        self._cache_set(self._cache_key(_PRODUCT_TOOL, arguments), row)
        return row

    def fetch_category_features(self, product_name: str) -> dict[str, Any]:
        if not isinstance(product_name, str) or not product_name.strip():
            raise ValueError("product_name must be a nonempty primary keyword")
        arguments = {"product_name": product_name.strip(), "amz_site": self.marketplace}
        cached = self._cache_get(self._cache_key(_FEATURE_TOOL, arguments))
        if cached is not None and isinstance(cached.get("features"), list):
            return cached
        row = normalize_category_feature_response(self._call(_FEATURE_TOOL, arguments))
        self._cache_set(self._cache_key(_FEATURE_TOOL, arguments), row)
        return row

    def estimate_required_calls(self, profile: Mapping[str, Any]) -> int:
        """Estimate uncached Sorftime calls for one profile without reserving.

        This is deliberately limited to the calls this adapter owns.  It does
        not guess calls made by Xiyou or the visual adapter, and it never
        increments usage counters.  The production composition root uses the
        estimate before enrichment so a task cannot start a partial Sorftime
        profile merely because the per-call ceiling was too small.
        """
        if not isinstance(profile, Mapping):
            raise ValueError("competitor profile must be an object")
        self_asin = str(profile.get("self_asin") or "").upper()
        competitors = profile.get("competitors")
        if not ASIN.fullmatch(self_asin) or not isinstance(competitors, list):
            raise ValueError("competitor profile identity is invalid")
        targets = [self_asin] + [str(row.get("asin") or "").upper()
                                  for row in competitors if isinstance(row, Mapping)]
        estimated = sum(1 for asin in dict.fromkeys(targets)
                        if ASIN.fullmatch(asin) and not self._cache_has_product(asin))
        primary_keyword = profile.get("primary_core_keyword")
        if not isinstance(primary_keyword, str) or not primary_keyword.strip():
            keywords = profile.get("core_keywords")
            if isinstance(keywords, list):
                primary_keyword = next((item for item in keywords
                                        if isinstance(item, str) and item.strip()), None)
        if isinstance(primary_keyword, str) and primary_keyword.strip() \
                and not self._cache_has_category_features(primary_keyword):
            estimated += 1
        return estimated

    def enrich_profile(self, profile: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(profile, Mapping):
            raise ValueError("competitor profile must be an object")
        self_asin = str(profile.get("self_asin") or "").upper()
        competitors = profile.get("competitors")
        if not ASIN.fullmatch(self_asin) or not isinstance(competitors, list):
            raise ValueError("competitor profile identity is invalid")
        result = deepcopy(dict(profile))
        self.last_category_features = None
        products: dict[str, dict[str, Any]] = {}
        calls_before = self.actual_calls
        cache_before = self.cache_hits
        retries_before = self.retries
        rate_limited_before = self.rate_limited
        failures_before = self.failures
        receipts_before = len(self.call_receipts)
        outcomes = []
        targets = [self_asin] + [str(row.get("asin") or "").upper() for row in competitors if isinstance(row, Mapping)]
        primary_keyword = result.get("primary_core_keyword")
        if not isinstance(primary_keyword, str) or not primary_keyword.strip():
            keywords = result.get("core_keywords")
            if isinstance(keywords, list):
                primary_keyword = next((item for item in keywords if isinstance(item, str) and item.strip()), None)
        estimated_calls = self.estimate_required_calls(profile) if self.preflight_whole_task else None
        preflight_blocked = False
        if self.preflight_whole_task:
            can_accept = getattr(self.budget, "can_accept_request", None)
            preflight_blocked = (not callable(can_accept)
                                 or can_accept(calls=estimated_calls) is not True)
        for asin in dict.fromkeys(targets):
            if not ASIN.fullmatch(asin):
                continue
            if preflight_blocked:
                status = "budget_exhausted"
            else:
                try:
                    products[asin] = self.fetch_product(asin)
                    status = "success" if any(products[asin].get(field) not in (None, "", []) for field in COMPARISON_FIELDS) else "no_result"
                except ValueError:
                    status = "schema_error"
                except RuntimeError as exc:
                    status = "budget_exhausted" if str(exc) == "Sorftime call budget exhausted" else "provider_error"
                except Exception:
                    status = "provider_error"
            outcomes.append({"asin": asin, "tool": _PRODUCT_TOOL, "status": status})
        def merge(row: Mapping[str, Any] | None, asin: str, role: str) -> dict[str, Any]:
            base = deepcopy(dict(row or {"asin": asin}))
            source = products.get(asin)
            if source:
                provenance = base.setdefault("field_provenance", {})
                for key, value in source.items():
                    if key in {"missing_fields", "gallery"}:
                        continue
                    if value not in (None, "", []) and key in COMPARISON_FIELDS + ("image_urls", "attributes", "description"):
                        # This adapter is the newer product snapshot source.
                        # Keep the previous value in provenance, but do not
                        # let an older nonempty title/price/bullet list hide
                        # the selected Sorftime snapshot.
                        use_new = True
                        reason = ("provider_gallery_priority" if key in {"image_urls", "main_image_url"}
                                  else "provider_snapshot_priority" if base.get(key) not in (None, "", [])
                                  else "fill_missing")
                        provenance[key] = {"previous": {"value": deepcopy(base.get(key)), "source": base.get("source"), "sampled_at": base.get("sampled_at")},
                                           "incoming": {"value": deepcopy(value), "source": source["source"], "sampled_at": source["sampled_at"]},
                                           "reason": reason}
                        provenance[key]["selected"] = deepcopy(provenance[key]["incoming" if use_new else "previous"])
                        if key == "image_urls" and isinstance(value, list) and value:
                            base[key] = deepcopy(value)
                        elif key == "main_image_url" and value:
                            base[key] = value
                        else:
                            base[key] = deepcopy(value)
                base["role"] = role
                base["source_refs"] = sorted(set((base.get("source_refs") or []) + source["source_refs"]))
                if source["gallery"]:
                    base["gallery"] = deepcopy(source["gallery"])
            base["missing_fields"] = [field for field in COMPARISON_FIELDS if base.get(field) in (None, "", [])
                                      and not (field == "main_image_url" and base.get("image_urls"))]
            base["provider_outcome"] = next((deepcopy(item) for item in outcomes if item["asin"] == asin), None)
            base["missing_reasons"] = {field: (base["provider_outcome"] or {}).get("status", "not_requested")
                                       if (base["provider_outcome"] or {}).get("status") != "success" else "not_returned"
                                       for field in base["missing_fields"]}
            return base
        result["self_product"] = merge(result.get("self_product"), self_asin, "self")
        result["competitors"] = [merge(row, str(row.get("asin")).upper(), "competitor") for row in competitors if isinstance(row, Mapping)]
        result["provider"] = "sorftime"
        if isinstance(primary_keyword, str) and primary_keyword.strip():
            if preflight_blocked:
                self.last_category_features = None
                result["category_features_error"] = "budget_exhausted"
            else:
                try:
                    self.last_category_features = self.fetch_category_features(primary_keyword)
                    self.last_category_features["primary_core_keyword"] = primary_keyword.strip()
                    self.last_category_features["marketplace"] = self.marketplace
                except Exception as exc:
                    # The product profile remains useful, but the category module
                    # is explicitly absent rather than an invented zero-feature set.
                    self.last_category_features = None
                    result["category_features_error"] = type(exc).__name__
        # Include product and category calls in the persisted profile counter.
        result["provider_calls"] = int(profile.get("provider_calls") or 0) + self.actual_calls - calls_before
        result["provider_outcomes"] = deepcopy(profile.get("provider_outcomes") or []) + outcomes
        result["provider_usage"] = {
            "actual_calls": self.actual_calls - calls_before,
            "cache_hits": self.cache_hits - cache_before,
            "retries": self.retries - retries_before,
            "rate_limited": self.rate_limited - rate_limited_before,
            "failures": self.failures - failures_before,
            "call_receipts": deepcopy(self.call_receipts[receipts_before:]),
        }
        if self.preflight_whole_task:
            result["provider_usage"]["estimated_calls"] = estimated_calls
        return result


class _LocalBudget:
    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.used = 0
        self._lock = threading.Lock()

    def reserve(self) -> bool:
        with self._lock:
            if self.used >= self.max_calls:
                return False
            self.used += 1
            return True

    def can_accept_request(self, *, calls: int = 1) -> bool:
        """Check remaining calls without consuming the budget.

        The production composition root uses this before claiming a queue
        lease.  Keep it separate from ``reserve`` so a pre-claim check cannot
        spend a Sorftime call by itself.
        """
        if type(calls) is not int or calls < 0:
            return False
        with self._lock:
            return self.used + calls <= self.max_calls


SorftimeCallBudget = _LocalBudget
