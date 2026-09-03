"""Deterministic multi-layer configuration merge for the strategy center."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


LAYER_ORDER = ("global", "store", "stage", "asin", "task")


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge nested mappings without mutating either input."""
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def effective_config(layers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Merge low-precedence layers into high-precedence layers."""
    unknown = set(layers) - set(LAYER_ORDER)
    if unknown:
        raise ValueError(f"unknown config layers: {sorted(unknown)}")
    result: dict[str, Any] = {}
    for layer in LAYER_ORDER:
        if layer in layers:
            result = deep_merge(result, layers[layer])
    return result


def config_version(config: Mapping[str, Any], *, schema_version: str = "config-0.1") -> str:
    """Create a stable version identifier from canonical JSON content."""
    payload = json.dumps({"schema_version": schema_version, "config": config}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "cfg-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

