#!/usr/bin/env python3
"""Build/audit an explicit live Pages bundle locally; never publish or call APIs."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pages_demo as demo

PUBLIC_CONFIG_FILES = frozenset({"public-config.js", "frontend/public-config.js"})
CONFIG_FIELDS = frozenset({"mode", "liveEnabled", "supabaseUrl", "publicKey", "gatewayUrl"})
ORIGIN_PATTERN = re.compile(r"https://([a-z0-9]{20})\.supabase\.co")
PUBLISHABLE_PATTERN = re.compile(r"sb_publishable_[A-Za-z0-9_-]{20,128}")
PUBLIC_KEY_PATTERN = re.compile(r"sb_publishable_[A-Za-z0-9_-]+")


def expected_live_files() -> set[str]:
    """Reuse the reviewed demo boundary, excluding every data artifact."""
    return {name for name in demo.expected_demo_files() if not name.startswith("data/")}


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JWT field")
        result[key] = value
    return result


def _decode_segment(segment: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        raise ValueError("invalid JWT encoding")
    decoded = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != segment:
        raise ValueError("noncanonical JWT encoding")
    return decoded


def validate_public_config(config: dict) -> dict:
    """Validate public deployment metadata without asserting remote key validity.

    Legacy anon JWTs are inspected, not cryptographically verified. Opaque
    publishable keys cannot be bound to a project without an external request.
    Error messages deliberately never contain caller-supplied values.
    """
    if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
        raise ValueError("public configuration requires exactly the five supported fields")
    if config["mode"] != "live" or config["liveEnabled"] is not True:
        raise ValueError("live mode and explicit boolean liveEnabled are required")
    origin = config["supabaseUrl"]
    match = ORIGIN_PATTERN.fullmatch(origin) if isinstance(origin, str) else None
    if not match:
        raise ValueError("supabaseUrl must be a canonical Supabase HTTPS origin")
    if config["gatewayUrl"] != origin + "/functions/v1/kwcc-gateway":
        raise ValueError("gatewayUrl must be the same project's exact kwcc-gateway endpoint")
    key = config["publicKey"]
    if not isinstance(key, str) or len(key) > 4096:
        raise ValueError("publicKey must be a publishable key or project-matched anon JWT")
    if PUBLISHABLE_PATTERN.fullmatch(key):
        if demo.SECRET_PATTERN.search(key):
            raise ValueError("publicKey contains forbidden credential material")
    else:
        try:
            header_part, payload_part, signature_part = key.split(".")
            header = json.loads(_decode_segment(header_part), object_pairs_hook=_unique_object)
            payload = json.loads(_decode_segment(payload_part), object_pairs_hook=_unique_object)
            signature = _decode_segment(signature_part)
            valid = (
                header == {"alg": "HS256", "typ": "JWT"}
                and isinstance(payload, dict)
                and {"iss", "ref", "role"} <= set(payload) <= {"iss", "ref", "role", "iat", "exp"}
                and payload["iss"] == "supabase"
                and payload["role"] == "anon"
                and payload["ref"] == match.group(1)
                and all(type(payload[field]) is int and payload[field] >= 0
                        for field in ("iat", "exp") if field in payload)
                and len(signature) == 32
            )
            if not valid:
                raise ValueError("invalid anon JWT")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValueError("publicKey must be a publishable key or project-matched anon JWT") from None
    return {name: config[name] for name in sorted(CONFIG_FIELDS)}


def render_public_config(config: dict) -> str:
    return "window.KWCC_PUBLIC_CONFIG = Object.freeze(" + json.dumps(
        validate_public_config(config), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ) + ");\n"


def audit_live_output(output: str | Path, public_config: dict) -> list[str]:
    """Audit against caller-approved config, never trust config read from the bundle."""
    try:
        approved = render_public_config(public_config).encode("utf-8")
    except ValueError:
        return ["invalid caller public configuration"]
    raw = Path(output)
    if demo._contains_symlink(raw):
        return ["output directory path must not contain a symbolic link"]
    destination = raw.resolve()
    if not destination.is_dir():
        return ["missing output directory"]
    expected = expected_live_files()
    directories = {parent.as_posix() for name in expected for parent in Path(name).parents
                   if parent != Path(".")}
    errors: list[str] = []
    present: set[str] = set()

    def walk(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            errors.append("output directory cannot be inspected")
            return
        for path in children:
            relative = path.relative_to(destination).as_posix()
            # Never traverse a linked directory, including Windows junctions.
            if demo._contains_symlink(path):
                errors.append(f"symlink is not allowed: {relative}")
                continue
            try:
                kind = path.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(kind):
                    if relative not in directories:
                        errors.append(f"directory outside static allowlist: {relative}")
                    walk(path)
                    continue
                if not stat.S_ISREG(kind):
                    errors.append(f"non-regular file is not allowed: {relative}")
                    continue
                present.add(relative)
                if relative not in expected:
                    errors.append(f"file outside static allowlist: {relative}")
                if (relative.startswith("data/") or path.suffix.lower() in
                        {".csv", ".tsv", ".xlsx", ".xls", ".env", ".pem", ".key", ".p12"}
                        or path.name.lower().startswith(".env") or "private" in relative.lower()):
                    errors.append(f"forbidden file: {relative}")
                content_bytes = path.read_bytes()
                if relative in PUBLIC_CONFIG_FILES:
                    if content_bytes == approved:
                        # The only exception: whole-file equality to validated serialization.
                        continue
                    errors.append(f"public configuration differs from approved config: {relative}")
                content = content_bytes.decode("utf-8")
            except (OSError, UnicodeError):
                errors.append(f"file cannot be audited as UTF-8: {relative}")
                continue
            if demo.SECRET_PATTERN.search(content) or PUBLIC_KEY_PATTERN.search(content):
                errors.append(f"secret-like content: {relative}")
            if demo.EXTERNAL_URL_PATTERN.search(content):
                errors.append(f"external URL: {relative}")
            if path.suffix.lower() == ".html":
                for reference in demo.HTML_REFERENCE_PATTERN.findall(content):
                    if reference.startswith(("#", "mailto:", "tel:")):
                        continue
                    try:
                        parsed = urlsplit(reference)
                        local_path = unquote(parsed.path)
                        if (parsed.scheme or parsed.netloc or "\\" in local_path
                                or local_path.startswith("/") or "\x00" in local_path):
                            raise ValueError("nonlocal reference")
                        target = path.parent / local_path if local_path else path
                        if demo._contains_symlink(target):
                            raise ValueError("linked reference")
                        target = target.resolve()
                        target.relative_to(destination)
                    except (OSError, ValueError):
                        errors.append(f"HTML reference escapes output or is unsafe: {relative}")
                    else:
                        if not target.is_file():
                            errors.append(f"broken local HTML reference: {relative}")

    walk(destination)
    errors.extend(f"missing allowlisted file: {name}" for name in sorted(expected - present))
    return errors


def _prepare_output(output: str | Path) -> Path:
    raw = Path(output)
    if demo._contains_symlink(raw):
        raise ValueError("output directory path must not contain a symbolic link")
    destination = raw.resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("output directory must be missing or empty")
    return destination


def _write_file(root: Path, name: str, content: bytes) -> None:
    target = root / name
    demo._assert_no_symlinks(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    demo._assert_no_symlinks(target)
    with target.open("xb") as stream:
        stream.write(content)


def build(output: str | Path, public_config: dict) -> Path:
    config_bytes = render_public_config(public_config).encode("utf-8")
    destination = _prepare_output(output)
    with tempfile.TemporaryDirectory(prefix="kwcc-live-pages-") as temporary:
        scratch = Path(temporary)
        demo_output = demo.build(scratch / "demo")
        staging = scratch / "live"
        staging.mkdir()
        for name in sorted(expected_live_files()):
            source = demo_output / name
            demo._assert_no_symlinks(source)
            content = config_bytes if name in PUBLIC_CONFIG_FILES else source.read_bytes()
            _write_file(staging, name, content)
        if audit_live_output(staging, public_config):
            raise ValueError("live staging audit failed")
        _prepare_output(destination)
        destination.mkdir(parents=True, exist_ok=True)
        demo._assert_no_symlinks(destination)
        for name in sorted(expected_live_files()):
            source = staging / name
            demo._assert_no_symlinks(source)
            _write_file(destination, name, source.read_bytes())
    if audit_live_output(destination, public_config):
        raise ValueError("live output audit failed")
    return destination


class _QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error includes unrecognized arguments, possibly keys.
        self.exit(2, "invalid CLI arguments; use --help (values omitted)\n")


def main(argv: list[str] | None = None) -> int:
    parser = _QuietParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--mode", default=os.environ.get("KWCC_MODE"))
    parser.add_argument("--live-enabled", default=os.environ.get("KWCC_LIVE_ENABLED"))
    parser.add_argument("--supabase-url", default=os.environ.get("KWCC_SUPABASE_URL"))
    parser.add_argument("--gateway-url", default=os.environ.get("KWCC_GATEWAY_URL"))
    args = parser.parse_args(argv)
    config = {"mode": args.mode, "liveEnabled": args.live_enabled == "true",
              "supabaseUrl": args.supabase_url, "gatewayUrl": args.gateway_url,
              "publicKey": os.environ.get("KWCC_PUBLIC_KEY")}
    passed = False
    try:
        validate_public_config(config)
        output = Path(args.output) if args.audit_only else build(args.output, config)
        passed = not audit_live_output(output, config)
    except (OSError, ValueError):
        # Never print exception values, keys, configuration, or secret filenames.
        pass
    summary = {"passed": passed, "published": False, "local_only": True,
               "network_calls": 0, "external_calls": 0}
    if passed:
        summary.update(file_count=len(expected_live_files()), contains_raw_inputs=False,
                       contains_demo_data=False)
    else:
        summary["error"] = "live configuration, build or output audit failed; values omitted"
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
