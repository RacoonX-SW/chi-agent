"""Role-specific path checks for a prospective Go CHI runtime.

This helper does not grant patient write authorization or create local tools.
"""
from __future__ import annotations

import re
from pathlib import Path

from evaluation_bundle import BundleFailure, _check_components

ROLES = {"provider", "payer", "cm"}
CASE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


def workspace_path(root: Path, value: str, role: str, *, directory: bool = False) -> Path | None:
    if role not in ROLES or type(value) is not str:
        return None
    root = Path(root)
    try:
        safe_root = _check_components(root, "resource_path_invalid")
        safe_path = _check_components(Path(value), "resource_path_invalid")
        parts = safe_path.relative_to(safe_root).parts
    except (BundleFailure, ValueError):
        return None
    if (len(parts) < (2 if directory else 3) or not CASE.fullmatch(parts[0])
            or parts[1] not in {role, "shared"}
            or any(part.startswith(".") or part.lower() in {"fixture", "fixtures", "verifier", "judge", "hidden", "private", "expectations"}
                   for part in parts[2:])):
        return None
    return safe_path
