"""Task API contract and legal state transitions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


STATUSES = {"pending", "processing", "completed", "failed"}
TRANSITIONS = {
    "pending": {"processing", "failed"},
    "processing": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _require(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _require_id(value: str, label: str) -> str:
    _require(value, label)
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")
    return value


@dataclass(frozen=True)
class FailureReason:
    code: str
    message: str
    stage: str
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "stage": self.stage, "retryable": self.retryable}


def transition(current: str, target: str) -> str:
    if current not in STATUSES or target not in STATUSES:
        raise ValueError("unknown task status")
    if target not in TRANSITIONS[current]:
        raise ValueError(f"illegal task transition: {current} -> {target}")
    return target


def create_task_contract(*, task_id: str, created_by: str, store_id: str, input_file_path: str, input_file_hash: str) -> dict[str, Any]:
    _require_id(task_id, "task_id")
    _require_id(created_by, "created_by")
    _require_id(store_id, "store_id")
    _require(input_file_path, "input_file_path")
    _require(input_file_hash, "input_file_hash")
    return {"task_id": task_id, "created_by": created_by, "store_id": store_id, "input_file_path": input_file_path, "input_file_hash": input_file_hash, "status": "pending", "current_stage": "ingestion"}


def rerun_contract(*, task_id: str, previous_run_id: str, run_id: str) -> dict[str, Any]:
    _require_id(task_id, "task_id")
    _require_id(previous_run_id, "previous_run_id")
    _require_id(run_id, "run_id")
    if run_id == previous_run_id:
        raise ValueError("run_id must differ from previous_run_id")
    return {"task_id": task_id, "run_id": run_id, "previous_run_id": previous_run_id, "status": "pending", "current_stage": "ingestion"}
