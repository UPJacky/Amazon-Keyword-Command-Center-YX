#!/usr/bin/env python3
"""Run bounded Python and PowerShell Worker loops locally without network access."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOOP_TIMEOUT_SECONDS = 30


def loop_timeout_seconds() -> int:
    value = os.environ.get("KWCC_LOOP_TIMEOUT_SECONDS", str(DEFAULT_LOOP_TIMEOUT_SECONDS))
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_LOOP_TIMEOUT_SECONDS
    return max(1, parsed)


def select_python() -> str:
    configured = os.environ.get("KWCC_PYTHON")
    if configured and Path(configured).is_file():
        return configured
    if importlib.util.find_spec("openpyxl") is not None:
        return sys.executable
    bundled = Path(r"C:\Users\Jacky\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
    return str(bundled) if bundled.is_file() else sys.executable


def run(command: list[str]) -> dict[str, object]:
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=loop_timeout_seconds())
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "passed": False,
            "timed_out": True,
            "heartbeats": 0,
            "stdout_tail": (exc.stdout or "")[-400:],
            "stderr_tail": (exc.stderr or "")[-400:],
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": None,
            "passed": False,
            "timed_out": False,
            "heartbeats": 0,
            "stdout_tail": "",
            "stderr_tail": f"unable to start loop gate: {exc}",
        }
    combined = f"{process.stdout}\n{process.stderr}"
    heartbeats = combined.count('"event": "worker_heartbeat"')
    summary = None
    try:
        summary = json.loads(process.stdout)
    except (TypeError, json.JSONDecodeError):
        pass
    bounded_summary = isinstance(summary, dict) and summary.get("cycles") == 2 and summary.get("errors") == 0 and summary.get("stopped") is False
    return {
        "command": command,
        "returncode": process.returncode,
        "passed": process.returncode == 0 and heartbeats >= 2 and bounded_summary,
        "timed_out": False,
        "heartbeats": heartbeats,
        "summary": summary,
        "stdout_tail": process.stdout[-400:],
        "stderr_tail": process.stderr[-400:],
    }


def main() -> int:
    python = select_python()
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="kwcc-loop-check-") as temporary:
        queue_root = str(Path(temporary) / "queue")
        storage_root = str(Path(temporary) / "storage")
        results.append(
            run(
                [
                    python,
                    "scripts/run_worker_loop.py",
                    "--queue-root",
                    queue_root,
                    "--storage-root",
                    storage_root,
                    "--poll-interval",
                    "0",
                    "--heartbeat-interval",
                    "0",
                    "--max-cycles",
                    "2",
                ]
            )
        )
        if powershell:
            results.append(
                run(
                    [
                        powershell,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(ROOT / "scripts" / "run_worker_loop.ps1"),
                        "-QueueRoot",
                        queue_root,
                        "-StorageRoot",
                        storage_root,
                        "-PollInterval",
                        "0",
                        "-HeartbeatInterval",
                        "0",
                        "-MaxCycles",
                        "2",
                    ]
                )
            )
        else:
            results.append({"passed": False, "reason": "PowerShell executable not found"})

    gate_count_ok = len(results) == 2
    passed = gate_count_ok and all(bool(item["passed"]) for item in results)
    print(json.dumps({"passed": passed, "checks": results, "gate_count": len(results), "expected_gate_count": 2, "gate_count_ok": gate_count_ok, "network_calls": 0, "external_calls": 0, "local_only": True}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
