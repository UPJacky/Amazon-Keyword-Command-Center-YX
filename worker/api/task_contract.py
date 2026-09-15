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
ASIN = re.compile(r"^B0[A-Z0-9]{8}$")
MARKETPLACE = re.compile(r"^[A-Z]{2}$")
INPUT_PATH = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}(?:/[A-Za-z0-9][A-Za-z0-9_-]{0,127}){0,7}/input\.(?:xlsx|csv)$"
)
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
PRODUCT_STAGES = {"new", "growth", "stable", "clearance", "seasonal_restart"}
MAX_INPUT_BYTES = 10 * 1024 * 1024


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


def create_task_contract(*, task_id: str, created_by: str, store_id: str,
                         self_asin: str, marketplace: str, product_stage: str,
                         input_file_path: str, input_file_hash: str,
                         input_size: int) -> dict[str, Any]:
    _require_id(task_id, "task_id")
    _require_id(created_by, "created_by")
    _require_id(store_id, "store_id")
    if not isinstance(self_asin, str) or not ASIN.fullmatch(self_asin):
        raise ValueError("self_asin must be a B0-prefixed ten-character ASIN")
    if not isinstance(marketplace, str) or not MARKETPLACE.fullmatch(marketplace):
        raise ValueError("marketplace must be an uppercase two-letter code")
    if not isinstance(product_stage, str) or product_stage not in PRODUCT_STAGES:
        raise ValueError("product_stage is invalid")
    if not isinstance(input_file_path, str) or not INPUT_PATH.fullmatch(input_file_path):
        raise ValueError("input_file_path must be a relative input.csv or input.xlsx object key")
    if not isinstance(input_file_hash, str) or not SHA256.fullmatch(input_file_hash):
        raise ValueError("input_file_hash must be a SHA-256 hex digest")
    if type(input_size) is not int or not 0 < input_size <= MAX_INPUT_BYTES:
        raise ValueError("input_size must be within the allowed upload limit")
    return {"task_id": task_id, "created_by": created_by, "store_id": store_id,
            "self_asin": self_asin, "marketplace": marketplace,
            "product_stage": product_stage, "input_file_path": input_file_path,
            "input_file_hash": input_file_hash.lower(), "input_size": input_size,
            "status": "pending", "current_stage": "ingestion"}


def rerun_contract(*, task_id: str, previous_run_id: str, run_id: str) -> dict[str, Any]:
    _require_id(task_id, "task_id")
    _require_id(previous_run_id, "previous_run_id")
    _require_id(run_id, "run_id")
    if run_id == previous_run_id:
        raise ValueError("run_id must differ from previous_run_id")
    return {"task_id": task_id, "run_id": run_id, "previous_run_id": previous_run_id, "status": "pending", "current_stage": "ingestion"}
