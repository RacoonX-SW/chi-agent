"""Deterministic L0 retrieval index over already-authorized text roots.

The index is built in memory from regular files; it never follows symlinks and
never writes to disk. A hit is a pointer: callers must re-read the original file
and check its hash before citing it.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

SCHEMA = "chi-retrieval-l0-v1"
HIT_SCHEMA = "chi-retrieval-hit-v1"
BLOCKED = {"fixture", "fixtures", "verifier", "judge", "hidden", "private",
           "expectations", "solution", "solutions"}
ROLE_ALIASES = {
    "provider": "provider", "provider-pa": "provider", "provider_pa": "provider",
    "payer": "payer", "payer-um": "payer", "payer_um": "payer", "um": "payer",
    "care-manager": "cm", "care_manager": "cm", "cm": "cm",
    "medical-library": "shared", "medical_library": "shared", "platform": "shared",
}
YEAR = re.compile(r"(?<!\d)(20[0-9]{2})(?!\d)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MAX_TEXT_BYTES = 2 * 1024 * 1024
_INDEX_CACHE = {}


def _cache_key(roots):
    parts = []
    for root in roots:
        path = Path(root)
        try:
            if path.is_file() and not path.is_symlink():
                stat = path.stat()
                parts.append((str(path), stat.st_mtime_ns, stat.st_size))
                continue
            latest = 0
            count = 0
            total = 0
            for directory, names, files in os.walk(path, followlinks=False):
                names[:] = [name for name in names if not name.startswith(".")
                            and name.lower() not in BLOCKED]
                for name in files:
                    item = Path(directory) / name
                    if item.is_symlink() or _blocked(item.relative_to(path)):
                        continue
                    try:
                        stat = item.stat()
                    except OSError:
                        continue
                    count += 1
                    total += stat.st_size
                    latest = max(latest, stat.st_mtime_ns)
            parts.append((str(path), latest, count, total))
        except OSError:
            parts.append((str(path), None, None, None))
    return tuple(parts)


def _blocked(relative: Path) -> bool:
    return any(part.startswith(".") or part.lower() in BLOCKED for part in relative.parts)


def _metadata(root: Path, path: Path) -> dict:
    relative = path.relative_to(root)
    parts = [part for part in relative.parts]
    role = next((ROLE_ALIASES[part.lower()] for part in parts
                 if part.lower() in ROLE_ALIASES), None)
    year = None
    for part in reversed(parts):
        match = YEAR.search(part)
        if match:
            year = int(match.group(1))
            break
    category = parts[-2] if len(parts) >= 2 else None
    return {
        "role": role,
        "category": category,
        "year": year,
        "service": path.stem,
        "doc_type": path.suffix.lower().lstrip(".") or None,
    }


def build_index(roots, *, read_text=None, max_files=2000, max_bytes=64 * 1024 * 1024,
                use_cache=True):
    if not isinstance(roots, (list, tuple)) or not roots:
        raise ValueError("chi_index_roots_invalid")
    key = _cache_key(roots)
    if use_cache and key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    entries = []
    scanned = 0
    total = 0
    for root in roots:
        root = Path(root)
        paths = []
        if root.is_file() and not root.is_symlink():
            paths = [root]
            base = root.parent
        elif root.is_dir() and not root.is_symlink():
            base = root
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.is_symlink() and not _blocked(path.relative_to(root)):
                    paths.append(path)
        else:
            continue
        for path in paths:
            if scanned >= max_files or total >= max_bytes:
                break
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > MAX_TEXT_BYTES:
                continue
            try:
                text = read_text(path) if read_text is not None else raw.decode("utf-8")
            except Exception:
                continue
            if type(text) is not str:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            section = None
            line = 1
            for number, value in enumerate(text.splitlines(), 1):
                match = HEADING.match(value)
                if match:
                    section = match.group(2)
                if number == 1:
                    line = 1
            title = next((match.group(2) for match in
                          (HEADING.match(value) for value in text.splitlines()) if match), path.stem)
            entries.append({
                "schema": HIT_SCHEMA,
                "path": str(path),
                "relative": str(path.relative_to(base)) if path != base else path.name,
                "title": title,
                "section": section,
                "line": line,
                "sha256": digest,
                "bytes": len(raw),
                "text": text,
                "metadata": _metadata(base, path),
            })
            scanned += 1
            total += len(raw)
    result = {"schema": SCHEMA, "entries": entries, "files": len(entries),
              "truncated": scanned >= max_files or total >= max_bytes}
    if use_cache:
        _INDEX_CACHE[key] = result
    return result


def _matches(entry, filters):
    metadata = entry["metadata"]
    for key in ("role", "category", "year", "service", "doc_type"):
        value = filters.get(key)
        if value is None:
            continue
        if key == "year":
            if metadata.get("year") != value:
                return False
        elif metadata.get(key) != value:
            return False
    return True


def search_index(index, query, *, filters=None, max_results=10, case_sensitive=False):
    if type(index) is not dict or index.get("schema") != SCHEMA \
            or type(index.get("entries")) is not list:
        raise ValueError("chi_index_invalid")
    if type(query) is not str or not query.strip():
        raise ValueError("chi_index_query_invalid")
    filters = filters if type(filters) is dict else {}
    needle = query if case_sensitive else query.casefold()
    hits = []
    omitted = 0
    for entry in index["entries"]:
        if not _matches(entry, filters):
            continue
        text = entry.get("text")
        if type(text) is not str:
            continue
        section = None
        for number, line in enumerate(text.splitlines(), 1):
            match = HEADING.match(line)
            if match:
                section = match.group(2)
            haystack = line if case_sensitive else line.casefold()
            if needle in haystack:
                if len(hits) >= max_results:
                    omitted += 1
                    continue
                hits.append({
                    "schema": HIT_SCHEMA,
                    "path": entry["path"],
                    "relative": entry["relative"],
                    "title": entry["title"],
                    "section": section,
                    "line": number,
                    "sha256": entry["sha256"],
                    "excerpt": line.strip()[:240],
                    "metadata": entry["metadata"],
                })
    return {"schema": SCHEMA, "query": query, "filters": filters,
            "hits": hits, "total_matches": len(hits) + omitted,
            "omitted": omitted, "truncated": bool(omitted)}


def read_hit(hit, *, read_text=None):
    """Re-read the original file and verify the hit hash before citing."""
    if type(hit) is not dict or type(hit.get("path")) is not str \
            or type(hit.get("sha256")) is not str:
        raise ValueError("chi_index_hit_invalid")
    path = Path(hit["path"])
    if path.is_symlink() or not path.is_file():
        raise ValueError("chi_index_hit_unreadable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != hit["sha256"]:
        raise ValueError("chi_index_stale")
    text = read_text(path) if read_text is not None else raw.decode("utf-8")
    return {"schema": HIT_SCHEMA, "path": str(path), "sha256": hit["sha256"],
            "section": hit.get("section"), "line": hit.get("line"), "text": text}
