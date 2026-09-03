"""Validation for user-editable business configuration."""

from __future__ import annotations

import math
from typing import Any, Mapping


REQUIRED_SECTIONS = ("evidence", "acos", "stop_loss", "market", "organic_defense", "diagnostics")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_config(config: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(config, Mapping):
        return ["config must be an object"]
    for section in REQUIRED_SECTIONS:
        if not isinstance(config.get(section), Mapping):
            errors.append(f"missing section: {section}")
    if "product_stage" in config and not isinstance(config["product_stage"], str):
        errors.append("product_stage must be a string")
    for version_key in ("schema_version", "config_version"):
        if version_key in config and not isinstance(config[version_key], str):
            errors.append(f"{version_key} must be a string")
    if isinstance(config.get("acos"), Mapping):
        acos = config["acos"]
        for name in ("target", "tolerance", "break_even"):
            value = acos.get(name)
            if not _finite_number(value) or not 0 <= value <= 1:
                errors.append(f"acos.{name} must be between 0 and 1")
        if all(name in acos for name in ("target", "tolerance", "break_even")) and not (acos["target"] <= acos["tolerance"] <= acos["break_even"]):
            errors.append("acos boundaries must be target <= tolerance <= break_even")
    if isinstance(config.get("stop_loss"), Mapping):
        for name in ("zero_order_clicks", "zero_order_spend"):
            value = config["stop_loss"].get(name)
            if not _finite_number(value) or value < 0:
                errors.append(f"stop_loss.{name} must be non-negative")
    if isinstance(config.get("evidence"), Mapping):
        evidence = config["evidence"]
        for name in ("preliminary_orders_min", "sufficient_orders_min", "preliminary_clicks_min", "sufficient_clicks_min"):
            value = evidence.get(name)
            if not _finite_number(value) or value < 0:
                errors.append(f"evidence.{name} must be non-negative")
        if all(_finite_number(evidence.get(name)) for name in ("preliminary_orders_min", "sufficient_orders_min")) and evidence["preliminary_orders_min"] > evidence["sufficient_orders_min"]:
            errors.append("evidence order boundaries must be preliminary <= sufficient")
        if all(_finite_number(evidence.get(name)) for name in ("preliminary_clicks_min", "sufficient_clicks_min")) and evidence["preliminary_clicks_min"] > evidence["sufficient_clicks_min"]:
            errors.append("evidence click boundaries must be preliminary <= sufficient")
    if isinstance(config.get("market"), Mapping):
        value = config["market"].get("high_opportunity_min")
        if not _finite_number(value) or not 0 <= value <= 1:
            errors.append("market.high_opportunity_min must be between 0 and 1")
    if isinstance(config.get("organic_defense"), Mapping):
        value = config["organic_defense"].get("core_max_rank")
        if not _finite_number(value) or value < 1:
            errors.append("organic_defense.core_max_rank must be at least 1")
    if isinstance(config.get("diagnostics"), Mapping):
        value = config["diagnostics"].get("low_cvr")
        if not _finite_number(value) or not 0 <= value <= 1:
            errors.append("diagnostics.low_cvr must be between 0 and 1")
    return errors
