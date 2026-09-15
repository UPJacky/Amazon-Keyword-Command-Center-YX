"""Provider admission estimates used before a Supabase run is claimed.

The preview is deliberately conservative.  It has only the small, non-secret
task projection returned by ``kwcc_preview_next_run`` and therefore cannot
know which report rows or persisted facts will be cache hits.  It must never
under-estimate a live request: the provider adapters still perform their
cache-aware, task-local preflight after the input is downloaded.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_ASIN = re.compile(r"^[A-Z0-9]{10}$")


def estimate_claim_requirements(
    task: Mapping[str, Any],
    *,
    xiyou_enabled: bool,
    sorftime_enabled: bool,
    visual_enabled: bool,
    retry_attempts: int = 1,
) -> dict[str, int]:
    """Return a fail-closed, pre-claim upper bound for one task.

    Xiyou's bounded production path can make one market request and one
    competitor snapshot request.  Sorftime needs one product request for the
    self ASIN and each selected competitor, plus one category-feature request
    when a primary keyword is present.  The visual production adapter makes
    one multimodal request for the complete image group.  These are process
    admission requirements, not usage receipts; actual receipts are produced
    by each adapter after cache lookup and settlement.
    """
    if not isinstance(task, Mapping):
        raise ValueError("preview task must be an object")
    if type(retry_attempts) is not int or retry_attempts < 1:
        raise ValueError("retry_attempts must be a positive integer")

    self_asin = task.get("self_asin")
    if not isinstance(self_asin, str) or not _ASIN.fullmatch(self_asin.upper()):
        raise ValueError("preview self_asin is invalid")

    raw_competitors = task.get("competitor_asins", [])
    if not isinstance(raw_competitors, list):
        raise ValueError("preview competitor_asins must be a list")
    competitors: list[str] = []
    for value in raw_competitors:
        if not isinstance(value, str) or not _ASIN.fullmatch(value.upper()):
            raise ValueError("preview competitor_asins contains an invalid ASIN")
        normalized = value.upper()
        if normalized == self_asin.upper() or normalized in competitors:
            raise ValueError("preview competitor_asins is not unique")
        competitors.append(normalized)
    if len(competitors) > 5:
        raise ValueError("preview competitor_asins exceeds the bounded limit")

    primary = task.get("primary_core_keyword")
    has_primary = isinstance(primary, str) and bool(primary.strip())

    # The preview does not have the downloaded report, so a valid task is
    # admitted against the maximum bounded Xiyou path.  A task-local cache
    # hit can later reduce this to zero without spending a request.
    xiyou_calls = 2 if xiyou_enabled else 0
    sorftime_calls = (1 + len(competitors) + int(has_primary)) if sorftime_enabled else 0
    visual_calls = 1 if visual_enabled else 0
    return {
        "xiyou_calls": xiyou_calls,
        "xiyou_credits": xiyou_calls,
        "sorftime_calls": sorftime_calls,
        "visual_calls": visual_calls,
        "total_calls": xiyou_calls + sorftime_calls + visual_calls,
        "xiyou_attempts": xiyou_calls * retry_attempts,
        "sorftime_attempts": sorftime_calls * retry_attempts,
        "visual_attempts": visual_calls * retry_attempts,
        "total_provider_attempts": (xiyou_calls + sorftime_calls + visual_calls) * retry_attempts,
    }
