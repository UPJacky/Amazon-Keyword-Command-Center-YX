"""Small JSON cache with explicit TTL and no implicit network refresh."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from worker.security.path_guard import contains_link_or_reparse


class ProviderCache:
    def __init__(self, root: str | Path, ttl_seconds: int):
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self._guard(self.root)

    @staticmethod
    def _guard(path: Path) -> None:
        if contains_link_or_reparse(path):
            raise ValueError("cache paths must not contain links or reparse points")

    @staticmethod
    def _timestamp(value: Any) -> float:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("cache timestamp must be finite and non-negative")
        return float(value)

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", key):
            raise ValueError("invalid cache key")
        path = self.root / f"{key}.json"
        self._guard(path)
        return path

    def get(self, key: str, now: float | None = None) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("invalid cache entry")
        current = self._timestamp(time.time() if now is None else now)
        created = self._timestamp(payload.get("created_at"))
        if created > current or current - created > self.ttl_seconds:
            return None
        return payload

    def set(self, key: str, *, provider: str, snapshot_version: str, data: dict[str, Any], now: float | None = None) -> Path:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._guard(path)
        if not isinstance(data, dict):
            raise ValueError("cache data must be an object")
        payload = {"provider": provider, "cache_key": key, "created_at": self._timestamp(time.time() if now is None else now), "snapshot_version": snapshot_version, "data": data}
        # Publish complete JSON atomically, including concurrent refreshes. A
        # reader observes either the previous entry or the complete new entry.
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".provider-cache-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(serialized)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path
