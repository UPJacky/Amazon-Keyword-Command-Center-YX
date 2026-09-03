"""Provider-independent task and run identity helpers for V1."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Task:
    """One user submission; reruns create Run objects instead of replacing it."""

    task_id: str = field(default_factory=_uuid)
    created_by: str | None = None
    store_id: str | None = None
    self_asin: str | None = None
    competitor_asins: tuple[str, ...] = ()
    core_keywords: tuple[str, ...] = ()
    product_stage: str | None = None
    input_file_path: str | None = None
    input_file_hash: str | None = None
    currency_code: str | None = None
    created_at: str = field(default_factory=_now)

    def artifact_root(self, run_id: str) -> str:
        return str(PurePosixPath("data") / self.task_id / run_id)


@dataclass(frozen=True)
class Run:
    """One actual execution associated with a task."""

    task_id: str
    run_id: str = field(default_factory=_uuid)
    previous_run_id: str | None = None
    rule_version: str | None = None
    config_version: str | None = None
    provider_snapshot_version: str | None = None
    status: str = "pending"
    created_at: str = field(default_factory=_now)

    def reproducibility_key(self, input_hash: str) -> str:
        values = "|".join((self.task_id, input_hash, self.rule_version or "", self.config_version or "", self.provider_snapshot_version or ""))
        return hashlib.sha256(values.encode("utf-8")).hexdigest()


def to_record(value: Task | Run) -> dict[str, Any]:
    """Return a JSON-friendly, deterministic record."""
    record = asdict(value)
    for key in ("competitor_asins", "core_keywords"):
        if key in record:
            record[key] = list(record[key])
    return record

