from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
TASK_STATUSES = frozenset(
    {
        "pending",
        "running",
        "completed",
        "blocked_external",
        "blocked_risk",
    }
)
EXECUTION_TYPES = frozenset({"local", "external"})
REQUIRED_TASK_FIELDS = (
    "id",
    "title",
    "status",
    "execution",
    "depends_on",
    "fingerprint_inputs",
    "input_fingerprint",
    "verified_fingerprint",
    "acceptance",
    "verification",
)
FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IGNORED_INPUT_PARTS = frozenset({".git", "__pycache__", ".pytest_cache"})
REQUIRED_VERIFICATION_FIELDS = ("kind", "source", "result", "summary")
AUTHORIZATION_RECEIPT_KIND = "authorization"
EXTERNAL_BLOCK_RECEIPT_KIND = "external_block"
SENSITIVE_RECEIPT_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    r"|\b(?:password|passwd|secret|service[_ -]?role(?:[_ -]?key)?|"
    r"access[_ -]?token|refresh[_ -]?token|api[_ -]?key|apikey)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


class LedgerValidationError(ValueError):
    """Raised when a project task ledger is not safe to supervise."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


# A concise alias is useful to callers without weakening the specific exception.
ValidationError = LedgerValidationError


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(value)


def _valid_fingerprint(value: Any, *, allow_empty: bool = False) -> bool:
    return isinstance(value, str) and (
        (allow_empty and value == "") or FINGERPRINT_PATTERN.fullmatch(value) is not None
    )


def _hash_record(digest: Any, label: str, payload: bytes) -> None:
    label_bytes = label.encode("utf-8")
    digest.update(len(label_bytes).to_bytes(8, "big"))
    digest.update(label_bytes)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)


def _safe_input_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise LedgerValidationError((f"unsafe fingerprint input path: {relative!r}",))
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise LedgerValidationError((f"fingerprint input escapes ledger root: {relative!r}",)) from exc
    if not resolved.exists():
        raise LedgerValidationError((f"fingerprint input does not exist: {relative!r}",))
    return resolved


def compute_task_fingerprint(task: dict[str, Any], root: str | Path) -> str:
    """Hash the task contract and declared inputs without mutating the ledger."""

    root_path = Path(root)
    digest = hashlib.sha256()
    _hash_record(digest, "format", b"project-task-fingerprint-v2")
    for field in ("id", "execution", "depends_on", "acceptance"):
        if field in task:
            payload = json.dumps(
                task[field], ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            _hash_record(digest, f"contract:{field}", payload)
    for index, item in enumerate(task["fingerprint_inputs"]):
        kind = item["kind"]
        if kind == "literal":
            _hash_record(digest, f"{index}:literal", item["value"].encode("utf-8"))
            continue

        relative = item["path"]
        source = _safe_input_path(root_path, relative)
        if source.is_file():
            files = [source]
        elif source.is_dir():
            files = sorted(
                path
                for path in source.rglob("*")
                if path.is_file()
                and not any(part in IGNORED_INPUT_PARTS for part in path.relative_to(root_path.resolve()).parts)
            )
        else:
            raise LedgerValidationError((f"fingerprint input is not a file or directory: {relative!r}",))
        if not files:
            raise LedgerValidationError((f"fingerprint input contains no files: {relative!r}",))
        for path in files:
            rel = path.relative_to(root_path.resolve()).as_posix()
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise LedgerValidationError((f"cannot read fingerprint input {rel!r}: {exc}",)) from exc
            _hash_record(digest, f"{index}:path:{rel}", payload)
    return f"sha256:{digest.hexdigest()}"


def _task_label(index: int, task: Any) -> str:
    if isinstance(task, dict) and isinstance(task.get("id"), str) and task["id"]:
        return f"task {task['id']!r}"
    return f"task at index {index}"


def _verification_errors(
    verification: Any, *, label: str, require_nonempty: bool
) -> list[str]:
    if not isinstance(verification, list):
        return [f"{label} must be an array"]
    if require_nonempty and not verification:
        return [f"{label} must be a non-empty array"]

    errors: list[str] = []
    for index, receipt in enumerate(verification):
        receipt_label = f"{label}[{index}]"
        if not isinstance(receipt, dict) or not receipt:
            errors.append(f"{receipt_label} must be a non-empty object")
            continue
        for field in REQUIRED_VERIFICATION_FIELDS:
            if not isinstance(receipt.get(field), str) or not receipt[field].strip():
                errors.append(f"{receipt_label}.{field} must be a non-empty string")
        if receipt.get("result") != "passed":
            errors.append(f"{receipt_label}.result must be 'passed'")
    return errors


def _external_event_receipt_errors(
    verification: Any, *, label: str, required_kind: str
) -> list[str]:
    """Validate an auditable external lifecycle event without persisting secrets."""

    errors = _verification_errors(
        verification,
        label=label,
        require_nonempty=True,
    )
    if errors or not isinstance(verification, list):
        return errors

    if not any(receipt.get("kind") == required_kind for receipt in verification):
        errors.append(f"{label} must include kind={required_kind!r}")
    allowed_fields = set(REQUIRED_VERIFICATION_FIELDS)
    for index, receipt in enumerate(verification):
        if not isinstance(receipt, dict):
            continue
        unknown = sorted(set(receipt) - allowed_fields)
        if unknown:
            errors.append(
                f"{label}[{index}] has unsupported fields: {', '.join(unknown)}"
            )
        for field in ("source", "summary"):
            value = receipt.get(field)
            if isinstance(value, str) and SENSITIVE_RECEIPT_PATTERN.search(value):
                errors.append(f"{label}[{index}].{field} appears to contain a secret")
    return errors


def _dependency_cycle(tasks_by_id: dict[str, dict[str, Any]]) -> list[str] | None:
    dependency_count = {
        task_id: len(task["depends_on"]) for task_id, task in tasks_by_id.items()
    }
    dependents: dict[str, list[str]] = {task_id: [] for task_id in tasks_by_id}
    for task_id, task in tasks_by_id.items():
        for dependency_id in task["depends_on"]:
            dependents[dependency_id].append(task_id)

    ready = deque(
        task_id for task_id in tasks_by_id if dependency_count[task_id] == 0
    )
    processed = 0
    while ready:
        task_id = ready.popleft()
        processed += 1
        for dependent_id in dependents[task_id]:
            dependency_count[dependent_id] -= 1
            if dependency_count[dependent_id] == 0:
                ready.append(dependent_id)

    if processed == len(tasks_by_id):
        return None

    remaining = {
        task_id for task_id in tasks_by_id if dependency_count[task_id] > 0
    }
    current = next(task_id for task_id in tasks_by_id if task_id in remaining)
    path: list[str] = []
    positions: dict[str, int] = {}
    while current not in positions:
        positions[current] = len(path)
        path.append(current)
        current = next(
            dependency_id
            for dependency_id in tasks_by_id[current]["depends_on"]
            if dependency_id in remaining
        )
    return path[positions[current] :] + [current]


def validate_ledger(ledger: Any) -> dict[str, Any]:
    """Validate schema version 1 and return the original ledger unchanged."""

    errors: list[str] = []
    if not isinstance(ledger, dict):
        raise LedgerValidationError(("ledger root must be a JSON object",))

    schema_version = ledger.get("schema_version")
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must be integer {SCHEMA_VERSION}")

    tasks = ledger.get("tasks")
    if not isinstance(tasks, list):
        errors.append("tasks must be a JSON array")
        raise LedgerValidationError(errors)
    if not tasks:
        errors.append("tasks must contain at least one task")
        raise LedgerValidationError(errors)

    tasks_by_id: dict[str, dict[str, Any]] = {}
    graph_fields_valid = True

    for index, task in enumerate(tasks):
        label = _task_label(index, task)
        if not isinstance(task, dict):
            errors.append(f"{label} must be a JSON object")
            graph_fields_valid = False
            continue

        missing = [field for field in REQUIRED_TASK_FIELDS if field not in task]
        if missing:
            errors.append(f"{label} missing required fields: {', '.join(missing)}")
        unknown = sorted(set(task) - set(REQUIRED_TASK_FIELDS))
        if unknown:
            errors.append(f"{label} has unknown fields: {', '.join(unknown)}")

        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            errors.append(f"{label} id must be a non-empty string")
            graph_fields_valid = False
        elif task_id in tasks_by_id:
            errors.append(f"duplicate task id: {task_id!r}")
            graph_fields_valid = False
        else:
            tasks_by_id[task_id] = task

        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label} title must be a non-empty string")

        status = task.get("status")
        if not isinstance(status, str) or status not in TASK_STATUSES:
            errors.append(
                f"{label} status must be one of: {', '.join(sorted(TASK_STATUSES))}"
            )

        execution = task.get("execution")
        if not isinstance(execution, str) or execution not in EXECUTION_TYPES:
            errors.append(
                f"{label} execution must be one of: {', '.join(sorted(EXECUTION_TYPES))}"
            )
        if status == "blocked_external" and execution != "external":
            errors.append(f"{label} blocked_external requires execution=external")

        dependencies = task.get("depends_on")
        if not isinstance(dependencies, list):
            errors.append(f"{label} depends_on must be an array of task IDs")
            graph_fields_valid = False
        else:
            seen_dependencies: set[str] = set()
            for dependency_id in dependencies:
                if not isinstance(dependency_id, str) or not dependency_id.strip():
                    errors.append(f"{label} depends_on entries must be non-empty strings")
                    graph_fields_valid = False
                elif dependency_id in seen_dependencies:
                    errors.append(f"{label} has duplicate dependency: {dependency_id!r}")
                    graph_fields_valid = False
                else:
                    seen_dependencies.add(dependency_id)

        fingerprint_inputs = task.get("fingerprint_inputs")
        if not isinstance(fingerprint_inputs, list) or not fingerprint_inputs:
            errors.append(f"{label} fingerprint_inputs must be a non-empty array")
        else:
            for input_index, item in enumerate(fingerprint_inputs):
                input_label = f"{label} fingerprint_inputs[{input_index}]"
                if not isinstance(item, dict):
                    errors.append(f"{input_label} must be an object")
                    continue
                kind = item.get("kind")
                expected_fields = {"kind", "value"} if kind == "literal" else {"kind", "path"}
                if kind not in {"literal", "path"}:
                    errors.append(f"{input_label} kind must be literal or path")
                    continue
                if set(item) != expected_fields:
                    errors.append(f"{input_label} fields must be: {', '.join(sorted(expected_fields))}")
                    continue
                value = item.get("value" if kind == "literal" else "path")
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{input_label} value must be a non-empty string")

        if not _valid_fingerprint(task.get("input_fingerprint")):
            errors.append(f"{label} input_fingerprint must be sha256:<64 lowercase hex>")
        if not _valid_fingerprint(task.get("verified_fingerprint"), allow_empty=True):
            errors.append(f"{label} verified_fingerprint must be empty or sha256:<64 lowercase hex>")

        acceptance = task.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance or not all(
            isinstance(item, str) and item.strip() for item in acceptance
        ):
            errors.append(f"{label} acceptance must be a non-empty array of strings")

        errors.extend(
            _verification_errors(
                task.get("verification"),
                label=f"{label} verification",
                require_nonempty=False,
            )
        )
        if status == "running" and execution == "external":
            errors.extend(
                _external_event_receipt_errors(
                    task.get("verification"),
                    label=f"{label} external authorization",
                    required_kind=AUTHORIZATION_RECEIPT_KIND,
                )
            )

    known_ids = set(tasks_by_id)
    running_ids = [
        task_id for task_id, task in tasks_by_id.items() if task.get("status") == "running"
    ]
    if len(running_ids) > 1:
        errors.append(f"multiple running tasks are not allowed: {', '.join(running_ids)}")
    if graph_fields_valid:
        for task_id, task in tasks_by_id.items():
            for dependency_id in task["depends_on"]:
                if dependency_id not in known_ids:
                    errors.append(
                        f"task {task_id!r} depends on missing task {dependency_id!r}"
                    )

        if not any("depends on missing task" in error for error in errors):
            cycle = _dependency_cycle(tasks_by_id)
            if cycle is not None:
                errors.append(f"dependency cycle detected: {' -> '.join(cycle)}")

    if errors:
        raise LedgerValidationError(errors)
    return ledger


def _is_effectively_completed(task: dict[str, Any], current_fingerprint: str) -> bool:
    return (
        task["status"] == "completed"
        and task["input_fingerprint"] == current_fingerprint
        and task["verified_fingerprint"] == current_fingerprint
        and _is_non_empty(task["verification"])
    )


def _next_task_payload(
    task: dict[str, Any], *, stale: bool, current_fingerprint: str
) -> dict[str, Any]:
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "execution": task["execution"],
        "depends_on": list(task["depends_on"]),
        "input_fingerprint": task["input_fingerprint"],
        "current_fingerprint": current_fingerprint,
        "acceptance": task["acceptance"],
        "stale": stale,
    }


def analyze_ledger(ledger: Any, root: str | Path = ".") -> dict[str, Any]:
    """Return a deterministic, read-only supervision decision for *ledger*."""

    validated = validate_ledger(ledger)
    tasks: list[dict[str, Any]] = validated["tasks"]
    current_fingerprints = {
        task["id"]: compute_task_fingerprint(task, root) for task in tasks
    }

    effective_completed = [
        task["id"]
        for task in tasks
        if _is_effectively_completed(task, current_fingerprints[task["id"]])
    ]
    effective_completed_set = set(effective_completed)
    stale = [
        task["id"]
        for task in tasks
        if task["status"] == "completed" and task["id"] not in effective_completed_set
    ]
    stale_set = set(stale)
    running_tasks = [task for task in tasks if task["status"] == "running"]
    running = [task["id"] for task in running_tasks]

    def dependencies_satisfied(task: dict[str, Any]) -> bool:
        return all(
            dependency_id in effective_completed_set
            for dependency_id in task["depends_on"]
        )

    runnable_tasks = [
        task
        for task in tasks
        if (task["status"] == "pending" or task["id"] in stale_set)
        and dependencies_satisfied(task)
    ]
    runnable = [task["id"] for task in runnable_tasks]

    local_runnable = [
        task
        for task in runnable_tasks
        if task["execution"] == "local"
    ]

    for task in running_tasks:
        if not dependencies_satisfied(task):
            raise LedgerValidationError(
                (f"running task {task['id']!r} has unsatisfied dependencies",)
            )

    ready_external: list[dict[str, Any]] = []
    ready_risk: list[dict[str, Any]] = []
    for task in tasks:
        if task["id"] in effective_completed_set:
            continue
        ready = dependencies_satisfied(task) or task["status"] == "running"
        if not ready:
            continue
        if task["status"] == "blocked_risk":
            ready_risk.append(task)
        elif task["status"] == "blocked_external" or (
            task["execution"] == "external"
            and (task["status"] in {"pending", "running"} or task["id"] in stale_set)
        ):
            ready_external.append(task)

    if running_tasks:
        execution_state = "RUNNING"
        selected = running_tasks[0]
        next_task = _next_task_payload(
            selected,
            stale=selected["id"] in stale_set,
            current_fingerprint=current_fingerprints[selected["id"]],
        )
    elif local_runnable:
        execution_state = "RUNNING"
        selected = local_runnable[0]
        next_task = _next_task_payload(
            selected,
            stale=selected["id"] in stale_set,
            current_fingerprint=current_fingerprints[selected["id"]],
        )
    elif len(effective_completed) == len(tasks):
        execution_state = "PROJECT_COMPLETE"
        next_task = None
    elif ready_external:
        execution_state = "BLOCKED_EXTERNAL"
        next_task = None
    elif ready_risk:
        execution_state = "BLOCKED_RISK"
        next_task = None
    else:  # A validated non-empty DAG must always have a ready unresolved task.
        raise RuntimeError("validated task graph has no resolvable supervision state")

    return {
        "schema_version": SCHEMA_VERSION,
        "execution_state": execution_state,
        "next_task": next_task,
        "next_task_id": None if next_task is None else next_task["id"],
        "task_count": len(tasks),
        "effective_completed": effective_completed,
        "stale": stale,
        "runnable": runnable,
        "running": running,
        "blocked_external": [task["id"] for task in ready_external],
        "blocked_risk": [task["id"] for task in ready_risk],
        "current_fingerprints": current_fingerprints,
    }


def supervise(ledger: Any, root: str | Path = ".") -> dict[str, Any]:
    """Public alias for callers that treat the module as a supervisor service."""

    return analyze_ledger(ledger, root=root)


def claim_next_task(
    ledger: dict[str, Any], root: str | Path = "."
) -> tuple[dict[str, Any], bool]:
    """Atomically claim semantics in memory; callers persist while holding a lock."""

    decision = analyze_ledger(ledger, root=root)
    next_task_id = decision["next_task_id"]
    if decision["execution_state"] != "RUNNING" or next_task_id is None:
        return decision, False

    task = next(item for item in ledger["tasks"] if item["id"] == next_task_id)
    if task["status"] == "running":
        # External work carries an explicit authorization receipt. A generic
        # local claim must never erase or silently refresh that authorization;
        # re-block and explicitly claim the external task again instead.
        if task["execution"] == "external":
            return decision, False
        current_fingerprint = decision["current_fingerprints"][next_task_id]
        if task["input_fingerprint"] == current_fingerprint:
            return decision, False
        task["input_fingerprint"] = current_fingerprint
        task["verified_fingerprint"] = ""
        task["verification"] = []
        return analyze_ledger(ledger, root=root), True

    task["status"] = "running"
    task["input_fingerprint"] = decision["current_fingerprints"][next_task_id]
    task["verified_fingerprint"] = ""
    task["verification"] = []
    return analyze_ledger(ledger, root=root), True


def _validate_completion_receipts(verification: Any) -> list[dict[str, Any]]:
    errors = _verification_errors(
        verification,
        label="completion verification",
        require_nonempty=True,
    )
    if errors:
        raise LedgerValidationError(errors)
    return verification


def _validate_external_event_receipts(
    verification: Any, *, label: str, required_kind: str
) -> list[dict[str, Any]]:
    errors = _external_event_receipt_errors(
        verification,
        label=label,
        required_kind=required_kind,
    )
    if errors:
        raise LedgerValidationError(errors)
    return verification


def claim_external_task(
    ledger: dict[str, Any],
    task_id: str,
    authorization: Any,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Explicitly claim one authorized external task; never auto-select it."""

    decision = analyze_ledger(ledger, root=root)
    task = next((item for item in ledger["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise LedgerValidationError(
            (f"cannot claim unknown external task {task_id!r}",)
        )
    if task["execution"] != "external":
        raise LedgerValidationError((f"task {task_id!r} is not external",))
    receipts = _validate_external_event_receipts(
        authorization,
        label="external authorization",
        required_kind=AUTHORIZATION_RECEIPT_KIND,
    )
    if decision["running"]:
        raise LedgerValidationError(
            (f"cannot claim external task while another task is running: {decision['running'][0]}",)
        )
    if decision["execution_state"] != "BLOCKED_EXTERNAL":
        raise LedgerValidationError(
            ("external work cannot be claimed while safe local work remains",)
        )
    if task_id not in decision["blocked_external"]:
        raise LedgerValidationError(
            (f"external task {task_id!r} is not ready or has unmet dependencies",)
        )
    if task["status"] not in {"blocked_external", "pending", "completed"}:
        raise LedgerValidationError(
            (f"external task {task_id!r} cannot be claimed from status {task['status']!r}",)
        )
    if task["status"] == "completed" and task_id not in decision["stale"]:
        raise LedgerValidationError(
            (f"external task {task_id!r} is already effectively completed",)
        )

    task["status"] = "running"
    task["input_fingerprint"] = decision["current_fingerprints"][task_id]
    task["verified_fingerprint"] = ""
    task["verification"] = receipts
    return analyze_ledger(ledger, root=root)


def block_external_task(
    ledger: dict[str, Any],
    task_id: str,
    reason: Any,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Return one running external task to a safe auditable blocked state."""

    validate_ledger(ledger)
    task = next((item for item in ledger["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise LedgerValidationError(
            (f"cannot block unknown external task {task_id!r}",)
        )
    if task["execution"] != "external":
        raise LedgerValidationError((f"task {task_id!r} is not external",))
    if task["status"] != "running":
        raise LedgerValidationError(
            (f"external task {task_id!r} is not running",)
        )
    running = [
        item["id"] for item in ledger["tasks"] if item["status"] == "running"
    ]
    if running != [task_id]:
        raise LedgerValidationError(
            (f"cannot safely block external task with running tasks: {', '.join(running)}",)
        )
    receipts = _validate_external_event_receipts(
        reason,
        label="external block reason",
        required_kind=EXTERNAL_BLOCK_RECEIPT_KIND,
    )

    task["status"] = "blocked_external"
    task["input_fingerprint"] = compute_task_fingerprint(task, root)
    task["verified_fingerprint"] = ""
    task["verification"] = receipts
    decision, _ = claim_next_task(ledger, root=root)
    return decision


def complete_task(
    ledger: dict[str, Any],
    task_id: str,
    verification: Any,
    root: str | Path = ".",
) -> dict[str, Any]:
    """Complete one running task and immediately claim the next safe local task."""

    analyze_ledger(ledger, root=root)
    task = next((item for item in ledger["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise LedgerValidationError((f"cannot complete unknown task {task_id!r}",))
    if task["status"] != "running":
        raise LedgerValidationError((f"task {task_id!r} is not running",))

    receipts = _validate_completion_receipts(verification)
    current_fingerprint = compute_task_fingerprint(task, root)
    if task["input_fingerprint"] != current_fingerprint:
        raise LedgerValidationError(
            (
                f"task {task_id!r} inputs changed while running; "
                "run --claim to refresh the claim, then revalidate",
            )
        )

    task["status"] = "completed"
    task["verified_fingerprint"] = current_fingerprint
    task["verification"] = receipts
    decision, _ = claim_next_task(ledger, root=root)
    return decision


def load_ledger(path: str | Path) -> dict[str, Any]:
    ledger_path = Path(path)
    try:
        text = ledger_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise LedgerValidationError((f"cannot read {ledger_path}: {exc}",)) from exc

    try:
        ledger = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LedgerValidationError(
            (
                f"invalid JSON in {ledger_path} at line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}",
            )
        ) from exc
    return validate_ledger(ledger)


@contextmanager
def _ledger_lock(ledger_path: Path):
    """Hold a cross-platform advisory lock without leaving a stale lock state."""

    lock_path = ledger_path.with_name(f".{ledger_path.name}.lock")
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LedgerValidationError(
                (f"task ledger is already locked: {ledger_path}",)
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _write_ledger_atomic(path: Path, ledger: dict[str, Any]) -> None:
    validate_ledger(ledger)
    serialized = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def claim_ledger_file(path: str | Path) -> dict[str, Any]:
    ledger_path = Path(path).resolve()
    with _ledger_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        decision, changed = claim_next_task(ledger, root=ledger_path.parent)
        if changed:
            _write_ledger_atomic(ledger_path, ledger)
        return decision


def claim_external_ledger_file(
    path: str | Path, task_id: str, authorization: Any
) -> dict[str, Any]:
    ledger_path = Path(path).resolve()
    with _ledger_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        decision = claim_external_task(
            ledger,
            task_id,
            authorization,
            root=ledger_path.parent,
        )
        _write_ledger_atomic(ledger_path, ledger)
        return decision


def block_external_ledger_file(
    path: str | Path, task_id: str, reason: Any
) -> dict[str, Any]:
    ledger_path = Path(path).resolve()
    with _ledger_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        decision = block_external_task(
            ledger,
            task_id,
            reason,
            root=ledger_path.parent,
        )
        _write_ledger_atomic(ledger_path, ledger)
        return decision


def complete_ledger_file(
    path: str | Path, task_id: str, verification: Any
) -> dict[str, Any]:
    ledger_path = Path(path).resolve()
    with _ledger_lock(ledger_path):
        ledger = load_ledger(ledger_path)
        decision = complete_task(
            ledger, task_id, verification, root=ledger_path.parent
        )
        _write_ledger_atomic(ledger_path, ledger)
        return decision


def _print_json(payload: dict[str, Any]) -> None:
    # ASCII-escaped JSON is stable across Windows console code pages.
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def _parse_json_argument(raw: str, label: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LedgerValidationError((f"invalid {label}: {exc.msg}",)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Supervisor for PROJECT_TASKS.json schema version 1."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--claim",
        action="store_true",
        help="atomically claim the selected safe local task",
    )
    action.add_argument(
        "--complete",
        metavar="TASK_ID",
        help="complete one running task and atomically claim its successor",
    )
    action.add_argument(
        "--claim-external",
        metavar="TASK_ID",
        help="atomically claim one explicitly authorized external task",
    )
    action.add_argument(
        "--block-external",
        metavar="TASK_ID",
        help="return one running external task to blocked_external",
    )
    parser.add_argument(
        "--verification-json",
        help="JSON array of passed verification receipts required by --complete",
    )
    parser.add_argument(
        "--authorization-json",
        help="non-sensitive authorization receipts required by --claim-external",
    )
    parser.add_argument(
        "--reason-json",
        help="non-sensitive block event receipts required by --block-external",
    )
    parser.add_argument(
        "ledger",
        nargs="?",
        default=Path("PROJECT_TASKS.json"),
        type=Path,
        help="task ledger path (default: PROJECT_TASKS.json)",
    )
    args = parser.parse_args(argv)

    try:
        ledger_path = args.ledger.resolve()
        if args.complete is not None:
            if args.verification_json is None:
                raise LedgerValidationError(
                    ("--complete requires --verification-json",)
                )
            if args.authorization_json is not None or args.reason_json is not None:
                raise LedgerValidationError(
                    ("--complete only accepts --verification-json",)
                )
            verification = _parse_json_argument(
                args.verification_json, "--verification-json"
            )
            decision = complete_ledger_file(
                ledger_path, args.complete, verification
            )
        elif args.claim_external is not None:
            if args.authorization_json is None:
                raise LedgerValidationError(
                    ("--claim-external requires --authorization-json",)
                )
            if args.verification_json is not None or args.reason_json is not None:
                raise LedgerValidationError(
                    ("--claim-external only accepts --authorization-json",)
                )
            authorization = _parse_json_argument(
                args.authorization_json, "--authorization-json"
            )
            decision = claim_external_ledger_file(
                ledger_path, args.claim_external, authorization
            )
        elif args.block_external is not None:
            if args.reason_json is None:
                raise LedgerValidationError(
                    ("--block-external requires --reason-json",)
                )
            if (
                args.verification_json is not None
                or args.authorization_json is not None
            ):
                raise LedgerValidationError(
                    ("--block-external only accepts --reason-json",)
                )
            reason = _parse_json_argument(args.reason_json, "--reason-json")
            decision = block_external_ledger_file(
                ledger_path, args.block_external, reason
            )
        elif (
            args.verification_json is not None
            or args.authorization_json is not None
            or args.reason_json is not None
        ):
            raise LedgerValidationError(
                ("JSON receipt flags require their matching lifecycle action",)
            )
        elif args.claim:
            decision = claim_ledger_file(ledger_path)
        else:
            decision = analyze_ledger(load_ledger(ledger_path), root=ledger_path.parent)
    except LedgerValidationError as exc:
        _print_json(
            {
                "schema_version": SCHEMA_VERSION,
                "execution_state": "INVALID",
                "next_task": None,
                "errors": list(exc.errors),
            }
        )
        return 2

    _print_json(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
