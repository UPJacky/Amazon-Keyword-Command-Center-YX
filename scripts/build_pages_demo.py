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
REPORT_PAGES = ("index", "rank", "negative", "competitors", "listing", "optimization")
CANONICAL_ROUTES = (
    "tool/index.html", "tool/tool.js",
    *(f"report/{name}.html" for name in REPORT_PAGES),
    *(f"report/{name}.js" for name in REPORT_PAGES if name != "index"),
    "report/shared.js",
)
ROOT_ASSETS = ("styles.css", "app.js", "report.js", "tasks.js", "strategy.js", "client.js")
DEMO_PUBLIC_CONFIG = 'window.KWCC_PUBLIC_CONFIG = Object.freeze({mode: "demo"});\n'
DEMO_DIRS = ("market-demo-report", "market-demo-modules")
DEMO_FILES = {
    "market-demo-report": ("master-table.json", "action-results.json", "report-meta.json"),
    "market-demo-modules": ("rank-benchmark.json", "negative-keywords.json", "competitors.json",
                            "listing-diagnostics.json", "optimization-plan.json"),
}
# Alias documents redirect before fetching data, so all report modules resolve
# scripts and fixture paths from the canonical report/ directory. Query strings
# and fragments survive historical bookmarked URLs and task report links.
LEGACY_ROUTES = {
    **{f"frontend/{name}": f"../../{name}" for name in CANONICAL_ROUTES if name.endswith(".html")},
    "frontend/report.html": "../report/index.html",
    "report.html": "report/index.html",
    **{name: f"frontend/{name}" for name in ("login.html", "workspace.html", "tasks.html", "strategy.html")},
}
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
HTML_REFERENCE_PATTERN = re.compile(r"(?:href|src|data-(?:login|post-login|report)-url)\s*=\s*[\"']([^\"']+)[\"']", re.I)


def expected_demo_files() -> set[str]:
    """The reviewed boundary, shared by packaging and downstream audits."""
    return {
        *(f"frontend/{name}" for name in FRONTEND_FILES),
        *CANONICAL_ROUTES, *ROOT_ASSETS, *LEGACY_ROUTES,
        *(f"data/golden/{directory}/{name}" for directory, names in DEMO_FILES.items() for name in names),
        "public-config.js", "rules/defaults/stable.json", "index.html", ".nojekyll",
    }


def _alias_document(target: str) -> str:
    return ('<!doctype html>\n<html lang="zh-CN"><meta charset="utf-8">'
            '<title>工作台入口</title>'
            f'<a href="{target}">进入工作台</a>'
            f'<script>location.replace({json.dumps(target)} + location.search + location.hash);</script>'
            '</html>\n')


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
    for name, target in LEGACY_ROUTES.items():
        alias = destination / name
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_text(_alias_document(target), encoding="utf-8")
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
        target = demo_root / directory
        target.mkdir()
        for name in DEMO_FILES[directory]:
            shutil.copy2(source / name, target / name)
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
    expected = expected_demo_files()
    present: set[str] = set()
    for path in destination.rglob("*"):
        relative = path.relative_to(destination).as_posix()
        if is_link_or_reparse(path):
            errors.append(f"symlink is not allowed: {relative}")
            continue
        if path.is_file():
            present.add(relative)
            if relative not in expected:
                errors.append(f"file outside static allowlist: {relative}")
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
                    local_path = reference.split("#", 1)[0].split("?", 1)[0]
                    target = (path.parent / local_path).resolve() if local_path else path
                    try:
                        target.relative_to(destination)
                    except ValueError:
                        errors.append(f"HTML reference escapes output: {relative} -> {reference}")
                    else:
                        if not target.is_file():
                            errors.append(f"broken local HTML reference: {relative} -> {reference}")
    errors.extend(f"missing allowlisted file: {relative}" for relative in sorted(expected - present))
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
