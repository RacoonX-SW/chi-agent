"""Inspect local imports and the dependency closure of each export allowlist."""
from __future__ import annotations

import argparse
import ast
import json
import re
from importlib.util import resolve_name
from pathlib import Path
from sys import stdlib_module_names

ROOT = Path(__file__).resolve().parents[2]

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
    if name.startswith("."):
        return "relative"
    top = name.split(".")[0]
    if not top:
        return "unknown"
    if name in self_modules:
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


def _module_imports(
    tree: ast.AST, package: str,
) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """Collect module-level and function/method-level imports.

    Class bodies are transparent: a method is still a function context, so an
    import inside ``class X: def run(...)`` is reported as nested under ``run``.
    """
    top: list[str] = []
    nested: list[tuple[str, str]] = []
    dynamic: list[tuple[str, str]] = []

    def imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]
        name = "." * node.level + (node.module or "")
        if not node.level or not package:
            return [name]
        try:
            base = resolve_name(name, package)
        except ImportError:
            return [name.lstrip(".")]
        if node.module:
            return [base]
        return [f"{base}.{alias.name}" for alias in node.names]

    def visit(node: ast.AST, function: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                names = imported_names(child)
                if function is None:
                    top.extend(names)
                else:
                    nested.extend((function, name) for name in names)
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.Call) and function is not None:
                target = getattr(child.func, "id", None) or getattr(child.func, "attr", None)
                if target in {"import_module", "__import__"}:
                    dynamic.append((function, target))
            visit(child, function)

    visit(tree, None)
    return [name for name in top if name], sorted(set(nested)), sorted(set(dynamic))


def _python_modules(root: Path) -> tuple[dict[str, Path], dict[str, set[str]]]:
    scripts = root / "scripts"
    if not scripts.is_dir():
        raise SystemExit("import_inventory: scripts directory missing")
    src = root / "src"
    if (src / "chi_agent").is_dir():
        bases = (
            (src, (src / "chi_agent").rglob("*.py")),
            (root, scripts.rglob("*.py")),
            (root / "docker/entrypoints", (root / "docker/entrypoints").glob("*.py")),
        )
        declarations = {"go": src / "chi_agent/bundle.py", "evaluation": src / "chi_agent/evaluation_bundle.py"}
        exported = False
    elif (scripts / "chi_agent").is_dir():
        bases = ((scripts, scripts.rglob("*.py")),)
        declarations = (
            {"go": scripts / "chi_agent/bundle.py"}
            if (scripts / "go_chi_entry.py").is_file()
            else {"evaluation": scripts / "chi_agent/evaluation_bundle.py"}
        )
        exported = True
    else:
        bases = ((scripts, scripts.glob("*.py")),)
        declarations = {"go": scripts / "go_chi_bundle.py", "evaluation": scripts / "evaluation_bundle.py"}
        exported = False

    modules = {}
    for base, paths in bases:
        for path in sorted(paths):
            parts = path.relative_to(base).with_suffix("").parts
            name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            modules[name] = path
    names_by_path = {path.relative_to(root).as_posix(): name for name, path in modules.items()}
    packages = {}
    for label, declaration in declarations.items():
        if declaration.is_file():
            mapping = _package_files(declaration)
            members = mapping.keys() if exported else mapping.values()
            packages[label] = {names_by_path[path] for path in members if path in names_by_path}
    return modules, packages


def _package_files(declaration: Path) -> dict[str, str]:
    for node in ast.parse(declaration.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        else:
            continue
        if getattr(target, "id", None) == "PACKAGE_FILES":
            return ast.literal_eval(node.value)
    raise SystemExit(f"import_inventory: PACKAGE_FILES missing in {declaration}")


def inventory(root: Path) -> dict:
    root = Path(root)
    paths, packages = _python_modules(root)
    self_modules = set(paths)
    locked = _locked_distributions(root)
    packaged = set().union(*packages.values())
    modules = {}
    local_imports = {}
    for name, path in paths.items():
        source = path.read_text(encoding="utf-8")
        package = name if path.stem == "__init__" else name.rpartition(".")[0]
        top, nested, dynamic = _module_imports(ast.parse(source), package)
        local_imports[name] = (set(top) | {target for _, target in nested}) & self_modules
        modules[name] = {
            "packaged": name in packaged,
            "lines": len(source.splitlines()),
            "top": sorted({_classify(name, self_modules, locked) + ":" + name for name in top}),
            "nested": sorted({_classify(name, self_modules, locked) + ":" + f"{func}:{name}"
                              for func, name in nested}),
            "dynamic": [f"{func}:{target}" for func, target in dynamic],
            "importers": [],
        }
    for name, targets in sorted(local_imports.items()):
        for target in targets - {name}:
            modules[target]["importers"].append(name)
    gaps = {
        (name, target)
        for members in packages.values()
        for name in members
        for target in local_imports[name] - members
    }
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
        "package_counts": {label: len(members) for label, members in packages.items()},
        "modules": modules,
        "closure_gaps": [{"module": name, "imports": target} for name, target in sorted(gaps)],
        "unknown_imports": unknown,
        "unlocked_externals": unlocked,
        "locked_distributions": len(locked),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-unknown", action="store_true")
    args = parser.parse_args(argv)
    result = inventory(args.root)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        counts = " ".join(f"{name}={count}" for name, count in result["package_counts"].items())
        print(f"modules={result['module_count']} packaged={result['packaged_count']} {counts}")
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
