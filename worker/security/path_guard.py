"""Filesystem checks that do not follow links or Windows reparse points."""

from __future__ import annotations

import stat
from pathlib import Path


def is_link_or_reparse(path: Path) -> bool:
    """Return true for symlinks, junctions, or other Windows reparse points."""
    try:
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return True
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, FileNotFoundError):
        return False
    except OSError:
        # A path that cannot be inspected must fail closed.  Treating an
        # access error as a safe ordinary path could allow a redirected or
        # reparse-point component to pass the boundary check.
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def contains_link_or_reparse(path: Path) -> bool:
    """Check every path component without resolving or following it."""
    current = path
    while current != current.parent:
        if is_link_or_reparse(current):
            return True
        current = current.parent
    return False


def present_without_following(path: Path) -> bool:
    """Treat dangling links and reparse points as occupied paths."""
    return path.exists() or is_link_or_reparse(path)
