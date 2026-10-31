"""Bounded, non-indexing text search over already-authorized local roots.

The caller decides which roots are allowed. This module only walks regular
files, skips symlinks/hidden and blocked names, and returns line-level hits
with a file hash. It never writes an index or follows links outside a root.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

SCHEMA = "chi-fs-search-v1"
MAX_QUERY = 200
MAX_FILES = 400
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_RESULTS = 20
MAX_EXCERPT = 240
BLOCKED = {"fixture", "fixtures", "verifier", "judge", "hidden", "private",
           "expectations", "solution", "solutions"}


class SearchRefusal(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _blocked(relative: Path) -> bool:
    return any(part.startswith(".") or part.lower() in BLOCKED for part in relative.parts)


def _iter_files(root: Path):
    if root.is_symlink():
        return
    if root.is_file():
        yield root
        return
    if not root.is_dir():
        return
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names
                          if not name.startswith(".") and name.lower() not in BLOCKED
                          and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or _blocked(path.relative_to(root)):
                continue
            yield path


def search(roots, query: str, *, max_results: int = 8, case_sensitive: bool = False,
           read_text=None) -> dict:
    if type(query) is not str or not query.strip() or len(query) > MAX_QUERY \
            or any(ord(char) < 32 for char in query):
        raise SearchRefusal("search_query_invalid")
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        raise SearchRefusal("search_arguments_invalid")
    if not isinstance(roots, (list, tuple)) or not roots:
        raise SearchRefusal("search_arguments_invalid")
    needle = query if case_sensitive else query.casefold()
    results, files_scanned, bytes_scanned, skipped, omitted = [], 0, 0, 0, 0
    truncated = False
    for root in roots:
        root = Path(root)
        for path in _iter_files(root):
            if files_scanned >= MAX_FILES:
                truncated = True
                break
            try:
                size = path.stat().st_size
            except OSError:
                skipped += 1
                continue
            if size > MAX_FILE_BYTES:
                skipped += 1
                continue
            if bytes_scanned + size > MAX_TOTAL_BYTES:
                truncated = True
                break
            if read_text is None:
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeError, OSError):
                    skipped += 1
                    continue
                raw = text.encode("utf-8")
            else:
                try:
                    text = read_text(path)
                except Exception:
                    text = None
                if not isinstance(text, str):
                    skipped += 1
                    continue
                raw = text.encode("utf-8")
            files_scanned += 1
            bytes_scanned += len(raw)
            digest = hashlib.sha256(raw).hexdigest()
            offset = 0
            for line_number, line in enumerate(text.splitlines(keepends=True), 1):
                haystack = line if case_sensitive else line.casefold()
                if needle in haystack:
                    if len(results) >= max_results:
                        omitted += 1
                        truncated = True
                        continue
                    excerpt = line.strip().replace("\x00", "")
                    results.append({
                        "path": str(path),
                        "line": line_number,
                        "byte_offset": offset,
                        "sha256": digest,
                        "excerpt": excerpt[:MAX_EXCERPT],
                        "excerpt_truncated": len(excerpt) > MAX_EXCERPT,
                    })
                offset += len(line.encode("utf-8"))
        if truncated:
            break
    return {
        "schema": SCHEMA,
        "query": query,
        "case_sensitive": bool(case_sensitive),
        "results": results,
        "no_matches": not results,
        "files_scanned": files_scanned,
        "bytes_scanned": bytes_scanned,
        "skipped_files": skipped,
        "omitted": omitted,
        "truncated": truncated,
        "limits": {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES,
                   "total_bytes": MAX_TOTAL_BYTES, "results": MAX_RESULTS,
                   "excerpt": MAX_EXCERPT},
    }
