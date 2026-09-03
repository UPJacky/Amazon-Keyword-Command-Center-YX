#!/usr/bin/env python3
"""Check syntax of every JavaScript file shipped by the static frontend."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SCRIPTS = ("app.js", "report.js", "tasks.js", "strategy.js", "client.js", "public-config.js", "tool/tool.js", "report/shared.js", "report/rank.js", "report/negative.js", "report/competitors.js", "report/listing.js", "report/optimization.js")


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("frontend_js_syntax: FAILED (node executable not found)")
        return 1
    failures: list[str] = []
    for name in SCRIPTS:
        path = FRONTEND / name
        if not path.is_file():
            failures.append(f"missing JavaScript asset: {name}")
            continue
        result = subprocess.run([node, "--check", str(path)], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            failures.append(f"{name}: {result.stderr.strip() or result.stdout.strip()}")
    if failures:
        print("frontend_js_syntax: FAILED")
        print("\n".join(failures))
        return 1
    print(f"frontend_js_syntax: PASSED ({len(SCRIPTS)} files); network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
