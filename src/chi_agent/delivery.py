"""Caller-owned delivery plan for the Go CHI package.

The runner does not download or install anything. The caller supplies the
package, pinned dependencies, official source checkout, public resources,
MCP endpoint, state/log paths and the one model credential. This module checks
that supply before a Trial starts and records a deterministic plan identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .bundle import BundleFailure, validate_bundle

SCHEMA = "chi-go-delivery-plan-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ROLE_PORT = {"provider": 8020, "payer": 8100, "cm": 8200}
MODEL_ENV = "OPENCODE_API_KEY"
FORBIDDEN_ENV = {
    "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY", "GEMINI_API_KEY", "GROK_API_KEY", "XAI_API_KEY",
    "OPENROUTER_API_KEY",
}
BLOCKED = {"fixture", "fixtures", "verifier", "judge", "hidden", "private",
           "expectations", "solution", "solutions"}
PLAN_KEYS = {"schema", "role", "bundle", "dependencies", "vendor", "resources",
             "mcp", "state", "history", "credentials"}


class DeliveryError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _object(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        raise DeliveryError(code)
    return value


def _text(value, code, limit=256):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise DeliveryError(code)
    return value


def _path(value, code):
    value = _text(value, code, 2048)
    path = PurePosixPath(value)
    if not value.startswith("/") or ".." in path.parts or any(part.startswith(".") for part in path.parts[1:]):
        raise DeliveryError(code)
    return value


def _blocked(path: Path) -> bool:
    return any(part.lower() in BLOCKED for part in path.parts)


def _regular(path: Path, code):
    try:
        if path.is_symlink() or not path.is_file():
            raise DeliveryError(code)
    except OSError:
        raise DeliveryError(code) from None


def _directory(path: Path, code):
    try:
        if path.is_symlink() or not path.is_dir():
            raise DeliveryError(code)
    except OSError:
        raise DeliveryError(code) from None


def validate_plan(value) -> dict:
    _object(value, PLAN_KEYS, "delivery_plan_invalid")
    if value["schema"] != SCHEMA or value["role"] not in ROLE_PORT:
        raise DeliveryError("delivery_plan_invalid")
    bundle = _object(value["bundle"], {"root", "sha256"}, "delivery_bundle_invalid")
    bundle = {"root": _path(bundle["root"], "delivery_bundle_invalid"),
              "sha256": _text(bundle["sha256"], "delivery_bundle_invalid", 64)}
    if not SHA256.fullmatch(bundle["sha256"]):
        raise DeliveryError("delivery_bundle_invalid")
    deps = _object(value["dependencies"], {"model_root", "pdf_root"}, "delivery_dependencies_invalid")
    deps = {key: _path(deps[key], "delivery_dependencies_invalid") for key in deps}
    vendor = _object(value["vendor"], {"root", "commit"}, "delivery_vendor_invalid")
    vendor = {"root": _path(vendor["root"], "delivery_vendor_invalid"),
              "commit": _text(vendor["commit"], "delivery_vendor_invalid", 40)}
    if not COMMIT.fullmatch(vendor["commit"]):
        raise DeliveryError("delivery_vendor_invalid")
    resources = _object(value["resources"], {"instruction", "handbook_root", "tool_references"},
                        "delivery_resources_invalid")
    resources = {"instruction": _path(resources["instruction"], "delivery_resources_invalid"),
                 "handbook_root": _path(resources["handbook_root"], "delivery_resources_invalid"),
                 "tool_references": resources["tool_references"]}
    if (type(resources["tool_references"]) is not list or not resources["tool_references"]
            or len(set(resources["tool_references"])) != len(resources["tool_references"])):
        raise DeliveryError("delivery_resources_invalid")
    resources["tool_references"] = [_path(item, "delivery_resources_invalid")
                                     for item in resources["tool_references"]]
    mcp = _object(value["mcp"], {"url", "role"}, "delivery_mcp_invalid")
    mcp = {"url": _text(mcp["url"], "delivery_mcp_invalid", 2048),
           "role": _text(mcp["role"], "delivery_mcp_invalid", 16)}
    if mcp["role"] != value["role"]:
        raise DeliveryError("delivery_mcp_invalid")
    try:
        parsed = urlsplit(mcp["url"])
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path != "/mcp"
                or parsed.port != ROLE_PORT[mcp["role"]] or any(ch.isspace() for ch in mcp["url"])):
            raise ValueError
    except (TypeError, ValueError):
        raise DeliveryError("delivery_mcp_invalid") from None
    state = _object(value["state"], {"output_root", "logs_dir"}, "delivery_state_invalid")
    state = {key: _path(state[key], "delivery_state_invalid") for key in state}
    history = _object(value["history"], {"mode", "q_root"}, "delivery_history_invalid")
    if history["mode"] not in {"local", "external"}:
        raise DeliveryError("delivery_history_invalid")
    if history["mode"] == "local":
        history = {"mode": "local", "q_root": _path(history["q_root"], "delivery_history_invalid")}
    else:
        if history["q_root"] is not None:
            raise DeliveryError("delivery_history_invalid")
        history = {"mode": "external", "q_root": None}
    credentials = _object(value["credentials"], {"model_env", "forbidden_env"},
                          "delivery_credentials_invalid")
    if credentials["model_env"] != MODEL_ENV:
        raise DeliveryError("delivery_credentials_invalid")
    forbidden = credentials["forbidden_env"]
    if type(forbidden) is not list or set(forbidden) != FORBIDDEN_ENV:
        raise DeliveryError("delivery_credentials_invalid")
    return {"schema": SCHEMA, "role": value["role"], "bundle": bundle,
            "dependencies": deps, "vendor": vendor, "resources": resources,
            "mcp": mcp, "state": state, "history": history,
            "credentials": {"model_env": MODEL_ENV,
                            "forbidden_env": sorted(FORBIDDEN_ENV)}}


def plan_digest(plan: dict) -> str:
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check_plan(value) -> dict:
    plan = validate_plan(value)
    bundle_root = Path(plan["bundle"]["root"])
    _directory(bundle_root, "delivery_bundle_missing")
    try:
        identity = validate_bundle(bundle_root)
    except (BundleFailure, OSError, ValueError):
        raise DeliveryError("delivery_bundle_identity_invalid") from None
    if identity.manifest_sha256 != plan["bundle"]["sha256"]:
        raise DeliveryError("delivery_bundle_identity_invalid")
    model_root = Path(plan["dependencies"]["model_root"])
    pdf_root = Path(plan["dependencies"]["pdf_root"])
    _directory(model_root / "agents", "delivery_dependencies_missing")
    _directory(pdf_root / "pypdf", "delivery_dependencies_missing")
    vendor_root = Path(plan["vendor"]["root"])
    _directory(vendor_root / "src" / "chi_bench", "delivery_vendor_missing")
    instruction = Path(plan["resources"]["instruction"])
    _regular(instruction, "delivery_instruction_invalid")
    if _blocked(instruction):
        raise DeliveryError("delivery_instruction_invalid")
    handbook = Path(plan["resources"]["handbook_root"])
    _directory(handbook, "delivery_handbook_invalid")
    if _blocked(handbook):
        raise DeliveryError("delivery_handbook_invalid")
    for item in plan["resources"]["tool_references"]:
        path = Path(item)
        _regular(path, "delivery_tool_reference_invalid")
        if _blocked(path):
            raise DeliveryError("delivery_tool_reference_invalid")
    output_root = Path(plan["state"]["output_root"])
    logs_dir = Path(plan["state"]["logs_dir"])
    if output_root.is_symlink():
        raise DeliveryError("delivery_state_invalid")
    if not output_root.parent.is_dir():
        raise DeliveryError("delivery_state_invalid")
    if logs_dir.exists() or logs_dir.is_symlink():
        raise DeliveryError("delivery_logs_exist")
    if plan["history"]["mode"] == "local":
        qroot = Path(plan["history"]["q_root"])
        _directory(qroot, "delivery_history_invalid")
        if output_root != qroot / "chi-evaluation":
            raise DeliveryError("delivery_history_invalid")
    return {
        "schema": "chi-go-delivery-check-v1",
        "status": "valid",
        "plan_sha256": plan_digest(plan),
        "role": plan["role"],
        "bundle_manifest_sha256": identity.manifest_sha256,
        "checks": ["bundle", "dependencies", "vendor", "instruction", "handbook",
                   "tool_references", "mcp", "state", "history", "credentials"],
        "network_install": False,
        "credential_names": [MODEL_ENV],
        "note": "caller supplies package/deps/vendor/resources/MCP/state; runner receives only the model key",
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check caller-owned Go CHI delivery supply")
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256")
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        normalized = validate_plan(plan)
        digest = plan_digest(normalized)
        if args.plan_sha256 is not None and args.plan_sha256 != digest:
            raise DeliveryError("delivery_plan_sha256_mismatch")
        report = check_plan(normalized)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (DeliveryError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "delivery_plan_invalid")
        print(json.dumps({"status": "invalid", "code": code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
