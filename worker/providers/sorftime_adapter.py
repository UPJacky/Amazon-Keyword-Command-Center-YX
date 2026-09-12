"""Adapter for the native Sorftime MCP product and category responses.

Sorftime returns JSON-RPC tool results as a content text block. This module
parses only the confirmed product_detail and similar_product_feature shapes,
keeps missing values explicit, and never exposes the query credential.
"""

from __future__ import annotations

import json
import re
import threading
from copy import deepcopy
from typing import Any, Mapping

from worker.competitors.category_features import normalize_category_features


ASIN = re.compile(r"^[A-Z0-9]{10}$")
_PRODUCT_TOOL = "product_detail"
_FEATURE_TOOL = "similar_product_feature"


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
    bullet_points = [item.strip() for item in bullet_points] if isinstance(bullet_points, list) else []
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
        "source": _PRODUCT_TOOL,
        "provider_sampled": True,
        "sampled_at": sampled_at,
        "source_refs": ["sorftime:product_detail"],
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
    """Fetch Sorftime product/category facts with one shared call ceiling."""

    def __init__(self, *, transport: Any, marketplace: str, max_calls: int = 5, budget: Any = None):
        if not callable(getattr(transport, "call", None)):
            raise ValueError("transport must provide call")
        if not isinstance(marketplace, str) or not re.fullmatch(r"[A-Z]{2}", marketplace):
            raise ValueError("marketplace must be an uppercase country code")
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.transport = transport
        self.marketplace = marketplace
        self.max_calls = max_calls
        self.budget = budget or _LocalBudget(max_calls)
        self.actual_calls = 0
        self.last_category_features: dict[str, Any] | None = None

    def _call(self, tool: str, arguments: dict[str, Any]) -> Mapping[str, Any]:
        if not self.budget.reserve():
            raise RuntimeError("Sorftime call budget exhausted")
        self.actual_calls += 1
        return self.transport.call(tool, arguments)

    def fetch_product(self, asin: str) -> dict[str, Any]:
        return normalize_product_detail(self._call(_PRODUCT_TOOL, {"asin": asin, "amz_site": self.marketplace}), asin=asin, marketplace=self.marketplace)

    def fetch_category_features(self, product_name: str) -> dict[str, Any]:
        if not isinstance(product_name, str) or not product_name.strip():
            raise ValueError("product_name must be a nonempty primary keyword")
        return normalize_category_feature_response(
            self._call(_FEATURE_TOOL, {"product_name": product_name.strip(), "amz_site": self.marketplace})
        )

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
        targets = [self_asin] + [str(row.get("asin") or "").upper() for row in competitors if isinstance(row, Mapping)]
        for asin in targets:
            if not ASIN.fullmatch(asin):
                continue
            try:
                products[asin] = self.fetch_product(asin)
            except Exception:
                # Preserve the existing partial row. The caller must inspect
                # missing_fields and provider_calls; failure is not success.
                continue
        def merge(row: Mapping[str, Any] | None, asin: str, role: str) -> dict[str, Any]:
            base = deepcopy(dict(row or {"asin": asin}))
            source = products.get(asin)
            if source:
                for key, value in source.items():
                    if key == "image_urls" and isinstance(value, list) and value:
                        base[key] = deepcopy(value)
                    elif key == "main_image_url" and value:
                        base[key] = value
                    elif key not in base or base.get(key) in (None, "", []):
                        base[key] = value
                base["role"] = role
                base["source_refs"] = sorted(set((base.get("source_refs") or []) + source["source_refs"]))
            return base
        result["self_product"] = merge(result.get("self_product"), self_asin, "self")
        result["competitors"] = [merge(row, str(row.get("asin")).upper(), "competitor") for row in competitors if isinstance(row, Mapping)]
        result["provider"] = "sorftime"
        primary_keyword = result.get("primary_core_keyword")
        if not isinstance(primary_keyword, str) or not primary_keyword.strip():
            keywords = result.get("core_keywords")
            if isinstance(keywords, list):
                primary_keyword = next((item for item in keywords if isinstance(item, str) and item.strip()), None)
        if isinstance(primary_keyword, str) and primary_keyword.strip():
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
        result["provider_calls"] = int(profile.get("provider_calls") or 0) + self.actual_calls
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


SorftimeCallBudget = _LocalBudget
