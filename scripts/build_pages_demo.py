#!/usr/bin/env python3
"""Build an allowlisted static demo site for future GitHub Pages publishing.

This packages only the frontend and explicitly reviewed demo artifacts. It
does not publish, contact GitHub, or copy raw/private task inputs.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker.security.path_guard import contains_link_or_reparse, is_link_or_reparse


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FILES = ("index.html", "login.html", "workspace.html", "tasks.html", "strategy.html", "report.html", "styles.css", "app.js", "report.js", "tasks.js", "strategy.js", "client.js", "public-config.js")
CANONICAL_ROUTES = ("tool/index.html", "tool/tool.js", "report/index.html")
ROOT_ASSETS = ("styles.css", "app.js", "report.js", "tasks.js", "strategy.js", "client.js")
DEMO_PUBLIC_CONFIG = 'window.KWCC_PUBLIC_CONFIG = Object.freeze({mode: "demo"});\n'
DEMO_DIRS = ("market-demo-report", "market-demo-modules")
SECRET_PATTERN = re.compile(
    # Denial code may name forbidden key types; detect credential values or
    # assignments, not those standalone validation literals.
    r"sb_secret_[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|AKID[A-Za-z0-9]{16,}|"
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:service_role|SUPABASE_SERVICE(?:_ROLE)?_KEY|DOUBAO_API_KEY|"
    r"XYDC_MCP_TOKEN|COS_SECRET_KEY|COS_SECRET_ID)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_-]{8,}",
    re.I,
)
EXTERNAL_URL_PATTERN = re.compile(r"https?://", re.I)
HTML_REFERENCE_PATTERN = re.compile(r"(?:href|src)=\"([^\"]+)\"", re.I)


def _contains_symlink(path: Path) -> bool:
    return contains_link_or_reparse(path)


def _assert_no_symlinks(path: Path) -> None:
    """Reject source trees before copy operations can follow a link."""
    if _contains_symlink(path):
        raise ValueError(f"source path must not contain a symbolic link: {path}")
    if path.is_dir():
        for child in path.rglob("*"):
            if is_link_or_reparse(child):
                raise ValueError(f"source tree contains a symbolic link: {child}")


def build(output: str | Path) -> Path:
    raw_destination = Path(output)
    if _contains_symlink(raw_destination):
        raise ValueError("output directory path must not contain a symbolic link")
    destination = raw_destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("output directory must be missing or empty")
    destination.mkdir(parents=True, exist_ok=True)
    if _contains_symlink(destination) or not destination.is_dir():
        raise ValueError("output directory must be a real directory")
    frontend = destination / "frontend"
    frontend.mkdir()
    if _contains_symlink(frontend) or not frontend.is_dir():
        raise ValueError("frontend output directory must be a real directory")
    for name in FRONTEND_FILES:
        source = ROOT / "frontend" / name
        _assert_no_symlinks(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        if name == "public-config.js":
            # A demo build never inherits a user's opt-in live deployment.
            (frontend / name).write_text(DEMO_PUBLIC_CONFIG, encoding="utf-8")
        else:
            shutil.copy2(source, frontend / name)
    for name in CANONICAL_ROUTES:
        source = ROOT / "frontend" / name
        _assert_no_symlinks(source)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for name in ROOT_ASSETS:
        source = ROOT / "frontend" / name
        _assert_no_symlinks(source)
        shutil.copy2(source, destination / name)
    (destination / "public-config.js").write_text(DEMO_PUBLIC_CONFIG, encoding="utf-8")
    demo_root = destination / "data" / "golden"
    demo_root.mkdir(parents=True)
    if _contains_symlink(demo_root) or not demo_root.is_dir():
        raise ValueError("demo output directory must be a real directory")
    for directory in DEMO_DIRS:
        source = ROOT / "data" / "golden" / directory
        _assert_no_symlinks(source)
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(source, demo_root / directory)
    rules = destination / "rules" / "defaults"
    rules.mkdir(parents=True)
    if _contains_symlink(rules) or not rules.is_dir():
        raise ValueError("rules output directory must be a real directory")
    stable_rules = ROOT / "rules" / "defaults" / "stable.json"
    _assert_no_symlinks(stable_rules)
    shutil.copy2(stable_rules, rules / "stable.json")
    shutil.copy2(ROOT / "frontend" / "index.html", destination / "index.html")
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    return destination


def audit_demo_output(output: str | Path) -> list[str]:
    """Validate the generated site boundary without contacting any service."""
    raw_destination = Path(output)
    if _contains_symlink(raw_destination):
        return ["output directory path must not contain a symbolic link"]
    destination = raw_destination.resolve()
    errors: list[str] = []
    if not destination.is_dir():
        return [f"missing output directory: {destination}"]
    public_configs = (destination / "frontend" / "public-config.js", destination / "public-config.js")
    if any(is_link_or_reparse(path) or not path.is_file() or path.read_text(encoding="utf-8") != DEMO_PUBLIC_CONFIG for path in public_configs):
        errors.append("demo public configuration must be the canonical offline config")
    for path in destination.rglob("*"):
        relative = path.relative_to(destination).as_posix()
        if is_link_or_reparse(path):
            errors.append(f"symlink is not allowed: {relative}")
            continue
        if path.is_file():
            if path.suffix.lower() in {".xlsx", ".csv", ".tsv", ".env"} or "private" in relative.lower():
                errors.append(f"forbidden file: {relative}")
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if SECRET_PATTERN.search(content):
                errors.append(f"secret-like content: {relative}")
            if EXTERNAL_URL_PATTERN.search(content):
                errors.append(f"external URL: {relative}")
            if path.suffix.lower() == ".html":
                for reference in HTML_REFERENCE_PATTERN.findall(content):
                    if reference.startswith(("#", "mailto:", "tel:", "javascript:")):
                        continue
                    target = (path.parent / reference.split("#", 1)[0]).resolve()
                    try:
                        target.relative_to(destination)
                    except ValueError:
                        errors.append(f"HTML reference escapes output: {relative} -> {reference}")
                    else:
                        if not target.is_file():
                            errors.append(f"broken local HTML reference: {relative} -> {reference}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(args.output)
    errors = audit_demo_output(result)
    files = [path.relative_to(result).as_posix() for path in result.rglob("*") if path.is_file()]
    if errors:
        raise SystemExit("demo output audit failed: " + "; ".join(errors))
    print(json.dumps({
        "passed": True,
        "file_count": len(files),
        "contains_raw_inputs": False,
        "published": False,
        "network_calls": 0,
        "external_calls": 0,
        "local_only": True,
    }, ensure_ascii=False))
