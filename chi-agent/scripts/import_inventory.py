"""Read-only import and packaging inventory for the Go CHI tree.

This tool answers three questions without importing project modules or touching
state:

1. Which self modules exist, and which of them are inside the inner bundle
   allowlist (`go_chi_bundle.PACKAGE_FILES`)?
2. Which modules import which self modules, including imports placed inside
   functions?
3. Does a packaged module import a self module that is not packaged?

It never rewrites files, never reads credentials, and exits non-zero when it
finds a closure gap or an unclassified import so CI can gate on it.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from sys import stdlib_module_names

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = "scripts"

# Import names that differ from the distribution name in the lock files.
IMPORT_ALIASES = {
    "agents": "openai-agents",
    "fitz": "pymupdf",
    "pymupdf": "pymupdf",
    "yaml": "pyyaml",
    "PIL": "pillow",
    "pydantic_core": "pydantic-core",
    "sse_starlette": "sse-starlette",
    "docker": "docker",
    "harbor": "harbor",
}
LOCK_FILES = ("requirements.lock", "requirements-harbor.lock", "requirements-model.lock", "requirements-pdf.lock")
VENDOR_PREFIXES = ("chi_bench",)
# Installed ad hoc in the controller image; not present in any requirements lock.
UNLOCKED_EXTERNALS = {"docker": "controller image only",
                      "huggingface_hub": "data download helper; not in repo locks"}


def _locked_distributions(root: Path) -> set[str]:
    names: set[str] = set()
    for name in LOCK_FILES:
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)==", line)
            if match:
                names.add(match.group(1).lower())
    return names


def _normalize(name: str) -> str:
    return name.split(".")[0].replace("_", "-").lower()


def _classify(name: str, self_modules: set[str], locked: set[str]) -> str:
    top = name.split(".")[0]
    if not top:
        return "unknown"
    if top in self_modules:
        return "self"
    if top in stdlib_module_names:
        return "stdlib"
    if top in VENDOR_PREFIXES:
        return "vendor"
    if top in UNLOCKED_EXTERNALS:
        return "unlocked_external"
    if IMPORT_ALIASES.get(top, top).replace("_", "-").lower() in locked or _normalize(top) in locked:
        return "third_party"
    return "unknown"


def _module_imports(tree: ast.AST) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    top: list[str] = []
    nested: list[tuple[str, str]] = []
    dynamic: list[tuple[str, str]] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            top.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            top.append(prefix + (node.module or ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    nested.extend((node.name, alias.name) for alias in sub.names)
                elif isinstance(sub, ast.ImportFrom):
                    prefix = "." * sub.level
                    nested.append((node.name, prefix + (sub.module or "")))
                elif isinstance(sub, ast.Call):
                    target = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    if target in {"import_module", "__import__"}:
                        dynamic.append((node.name, target))
    return [name for name in top if name], sorted(set(nested)), sorted(set(dynamic))


def inventory(root: Path) -> dict:
    root = Path(root)
    scripts = root / SCRIPTS
    if not scripts.is_dir():
        raise SystemExit("import_inventory: scripts directory missing")
    paths = sorted(scripts.glob("*.py"))
    self_modules = {path.stem for path in paths}
    locked = _locked_distributions(root)
    packaged: set[str] = set()
    bundle = scripts / "go_chi_bundle.py"
    if bundle.is_file():
        tree = ast.parse(bundle.read_text(encoding="utf-8"))
        for node in tree.body:
            target = (node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1
                      else node.target if isinstance(node, ast.AnnAssign) else None)
            if getattr(target, "id", None) == "PACKAGE_FILES":
                try:
                    mapping = ast.literal_eval(node.value)
                except ValueError:
                    break
                packaged = {Path(src).stem for src in mapping.values()
                            if src.startswith("scripts/") and src.endswith(".py")}
                break
    modules = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top, nested, dynamic = _module_imports(tree)
        modules[path.stem] = {
            "packaged": path.stem in packaged,
            "lines": len(path.read_text(encoding="utf-8").splitlines()),
            "top": sorted({_classify(name, self_modules, locked) + ":" + name for name in top}),
            "nested": sorted({_classify(name, self_modules, locked) + ":" + f"{func}:{name}"
                              for func, name in nested}),
            "dynamic": [f"{func}:{target}" for func, target in dynamic],
            "importers": [],
        }
    for name, record in modules.items():
        for other, candidate in modules.items():
            if other == name:
                continue
            names = {entry.split(":", 1)[1] for entry in candidate["top"] if entry.startswith("self:")}
            names |= {entry.split(":", 2)[2] for entry in candidate["nested"] if entry.startswith("self:")}
            if name in names:
                record["importers"].append(other)
        record["importers"].sort()
    gaps = []
    for name, record in modules.items():
        if not record["packaged"]:
            continue
        targets = {entry.split(":", 1)[1] for entry in record["top"] if entry.startswith("self:")}
        targets |= {entry.split(":", 2)[2] for entry in record["nested"] if entry.startswith("self:")}
        for target in sorted(targets):
            if target not in packaged:
                gaps.append({"module": name, "imports": target})
    unknown = []
    for name, record in modules.items():
        names = [entry.split(":", 1)[1] for entry in record["top"] if entry.startswith("unknown:")]
        names += [entry.split(":", 2)[2] for entry in record["nested"] if entry.startswith("unknown:")]
        if names:
            unknown.append({"module": name, "imports": sorted(set(names))})
    unlocked = []
    for name, record in modules.items():
        names = [entry.split(":", 1)[1] for entry in record["top"] if entry.startswith("unlocked_external:")]
        names += [entry.split(":", 2)[2] for entry in record["nested"] if entry.startswith("unlocked_external:")]
        if names:
            unlocked.append({"module": name, "imports": sorted(set(names))})
    return {
        "root": str(root),
        "module_count": len(modules),
        "packaged_count": len(packaged),
        "modules": modules,
        "closure_gaps": gaps,
        "unknown_imports": unknown,
        "unlocked_externals": unlocked,
        "locked_distributions": len(locked),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only import inventory for the Go CHI tree")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-unknown", action="store_true")
    args = parser.parse_args(argv)
    result = inventory(args.root)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"modules={result['module_count']} packaged={result['packaged_count']}")
        for gap in result["closure_gaps"]:
            print(f"GAP {gap['module']} -> {gap['imports']}")
        for item in result["unknown_imports"]:
            print(f"UNKNOWN {item['module']}: {', '.join(item['imports'])}")
        for item in result["unlocked_externals"]:
            print(f"UNLOCKED {item['module']}: {', '.join(item['imports'])}")
    if result["closure_gaps"]:
        return 1
    if result["unknown_imports"] and not args.allow_unknown:
        return 1
    if result["unlocked_externals"] and not args.allow_unknown:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
