#!/usr/bin/env python3
"""Identified Go CHI runner; all task resources and persistent state are external."""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).absolute().parent.parent
sys.dont_write_bytecode = True

from evaluation_bundle import BundleFailure, _check_components, _read_regular_bounded
from go_chi_bundle import validate_bundle
from go_chi_journal import ChiJournal, publish_b_receipt
from go_chi_local import acquire_existing_history
from go_chi_policy import TIME_POLICY, FEE_POLICY, RECOVERY_POLICY
from opencode_go_provider import GoFailure, INSTRUCTION, SYSTEM, load_profile

CONFIG = {"schema": "chi-go-evaluation-entry-v1", "provider_profile_id": "opencode-go-deepseek-v4.1-flash-v1",
          "policy_mode": "record_only", "hard_cap_usd": None, "chi_max_requests": 50,
          "chi_max_output_tokens": 8192, "confirmation_max_requests": 2,
          "confirmation_max_output_tokens": 32768, "coding_b_max_requests": 6,
          "coding_b_max_output_tokens": 1024, "automatic_retries": 0, "time_policy": TIME_POLICY, "fee_policy": FEE_POLICY,
          "output_recovery_policy": RECOVERY_POLICY}
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _same(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _identity(expected):
    from model_runner_adapter import _sdk_identity, _upstream_identity
    from pdf_resource_reader import dependency_identity
    if type(expected) is not str or not DIGEST.fullmatch(expected):
        raise GoFailure("chi_manifest_identity_required")
    identity = validate_bundle(ROOT)
    if identity.manifest_sha256 != expected:
        raise GoFailure("chi_manifest_identity_mismatch")
    raw = _read_regular_bounded(ROOT / "profiles/go-chi-entry.json", 16384, "chi_config_invalid")
    try:
        config = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not _same(config, CONFIG): raise ValueError
    except Exception:
        raise GoFailure("chi_config_invalid") from None
    load_profile()
    sdk = _sdk_identity()
    if sdk.get("httpx") != "0.28.1":
        raise GoFailure("chi_sdk_identity_mismatch")
    for name, version in {"mcp": "1.30.0", "jsonschema": "4.26.0", "pydantic": "2.14.1",
                          "pydantic-core": "2.50.1", "httpcore": "1.0.9"}.items():
        try:
            if importlib.metadata.version(name) != version:
                raise ValueError
        except Exception:
            raise GoFailure("chi_sdk_identity_mismatch") from None
        sdk[name] = version
    upstream = _upstream_identity()
    pdf = dependency_identity(ROOT / "requirements-pdf.lock")
    sdk_sources = {}
    for module in ("agents", "openai", "httpx", "httpcore", "mcp", "jsonschema", "pydantic"):
        try:
            spec = importlib.util.find_spec(module)
            if spec is None or spec.origin is None:
                raise ValueError
            directory = Path(spec.origin).parent
            digest = hashlib.sha256()
            entries = list(directory.rglob("*"))
            if any(path.is_symlink() for path in entries):
                raise ValueError
            files = sorted(path for path in entries if path.suffix in {".py", ".pyc", ".so"})
            if not files or len(files) > 10000:
                raise ValueError
            for path in files:
                if path.is_symlink() or not path.is_file():
                    raise ValueError
                relative = path.relative_to(directory).as_posix()
                digest.update(relative.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
            sdk_sources[module] = digest.hexdigest()
        except Exception:
            raise GoFailure("chi_sdk_identity_unavailable") from None
    data = {"bundle_manifest_sha256": identity.manifest_sha256, "sdk": sdk, "sdk_sources_sha256": sdk_sources,
            "upstream": upstream, "pdf": pdf}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest(), data


def _path(value, *, exists=False):
    try:
        return _check_components(Path(value), "chi_path_invalid", final_may_be_missing=not exists)
    except BundleFailure:
        raise GoFailure("chi_path_invalid") from None


def _disjoint(a, b):
    return a != b and a not in b.parents and b not in a.parents


def _url(value):
    try:
        parsed = urlsplit(value)
        if (len(value) > 2048 or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path != "/mcp" or parsed.port is None or not 1 <= parsed.port <= 65535
                or "?" in value or "#" in value or any(ch.isspace() for ch in value)):
            raise ValueError
    except Exception:
        raise GoFailure("chi_mcp_url_invalid") from None
    return value


def _instruction(path):
    path = _path(path, exists=True)
    if (any(part.lower() in {"fixtures", "fixture", "hidden", "private", "verifier"} for part in path.parts)
            or path.name.lower() in {"tasks.jsonl", "task.jsonl", "expected.jsonl", ".env"}
            or path.name.startswith(".")):
        raise GoFailure("chi_instruction_forbidden")
    try:
        raw = _read_regular_bounded(path, 65536, "chi_instruction_invalid")
        text = raw.decode("utf-8")
        if not text.strip() or "\x00" in text: raise ValueError
    except Exception:
        raise GoFailure("chi_instruction_invalid") from None
    return path, text


def _handbook_digest(root: Path) -> str:
    digest = hashlib.sha256()
    try:
        paths = sorted(root.rglob("*"))
        if len(paths) > 10000: raise ValueError
        total = 0
        count = 0
        for path in paths:
            relative = path.relative_to(root)
            if any(part.startswith(".") or part.lower() in {"fixture", "fixtures", "verifier", "judge", "hidden", "private", "expectations"}
                   for part in relative.parts):
                continue
            if path.is_symlink(): raise ValueError
            if path.is_dir(): continue
            raw = _read_regular_bounded(path, 16 * 1024 * 1024, "chi_handbook_invalid")
            count += 1
            total += len(raw)
            if total > 64 * 1024 * 1024: raise ValueError
            digest.update(relative.as_posix().encode() + b"\0" + hashlib.sha256(raw).digest())
        if count == 0: raise ValueError
    except Exception:
        raise GoFailure("chi_handbook_invalid") from None
    return digest.hexdigest()


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "coding-b", "live", "audit-history", "rebind-history", "inspect-history", "acknowledge-unsettled", "reconcile-provider"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--evaluation-id")
    parser.add_argument("--task-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--history-mode", choices=("local", "external"))
    parser.add_argument("--local-q-root", type=Path)
    parser.add_argument("--expected-old-identity")
    parser.add_argument("--expected-accounting-sha256")
    parser.add_argument("--migration-reason")
    parser.add_argument("--provider-record", type=Path)
    parser.add_argument("--provider-record-sha256")
    parser.add_argument("--target-run")
    parser.add_argument("--target-round", type=int)
    parser.add_argument("--expected-request-sha256")
    parser.add_argument("--acknowledgement-reason")
    parser.add_argument("--output-recovery", choices=(RECOVERY_POLICY["version"],), default=None)
    parser.add_argument("--role", choices=("provider", "payer", "cm"))
    parser.add_argument("--instruction-file", type=Path)
    parser.add_argument("--mcp-url")
    parser.add_argument("--workspace-root", type=Path, default=Path("/logs/artifacts/workspaces"))
    parser.add_argument("--handbook-root", type=Path, default=Path("/workspace/skills/managed-care-operations-handbook"))
    parser.add_argument("--tool-reference", type=Path, action="append", default=[])
    return parser


async def _run_b(journal, secret):
    import httpx
    from openai import AsyncOpenAI
    from agents.models.openai_chatcompletions import Converter
    from go_chi_guard import ChiGuard
    from go_chi_runtime import coding_tools, run_coding_b
    holder = {}
    tools = coding_tools(lambda: holder["guard"])
    session = "chi-" + uuid.uuid4().hex
    guard = ChiGuard(journal, secret, session, httpx.AsyncHTTPTransport(retries=0, verify=True),
                     tools=[Converter.tool_to_openai(tool) for tool in tools], system=SYSTEM, instruction=INSTRUCTION,
                     claimed=lambda: False, confirmation=lambda: None)
    holder["guard"] = guard
    client = AsyncOpenAI(api_key=secret, base_url="https://opencode.ai/inference/go/openai/v1",
        default_headers={"User-Agent": "chi-agent", "X-OpenCode-Session": session}, max_retries=0,
        http_client=httpx.AsyncClient(transport=guard, trust_env=False, follow_redirects=False,
                                      timeout=httpx.Timeout(float(TIME_POLICY['main_read_seconds']),
                                                            connect=float(TIME_POLICY['connect_seconds']))))
    try:
        return await run_coding_b(client, guard, tools)
    finally:
        await client.close()


def main(argv=None, *, development=None):
    args = _parser().parse_args(argv)
    q = journal = None
    b_receipt = None
    output = {"status": "blocked", "official_reward": None}
    try:
        if args.output_recovery is not None and args.mode != "live":
            raise GoFailure("chi_recovery_invalid")
        identity, identity_detail = _identity(args.bundle_sha256)
        if args.mode == "preflight":
            import importlib
            for module in ("go_chi_context", "go_chi_recovery", "go_chi_guidance", "go_chi_search", "go_chi_state",
                           "go_chi_guard", "go_chi_mcp", "go_chi_tools", "go_chi_runtime"):
                loaded = importlib.import_module(module)
                path = Path(getattr(loaded, "__file__", "")).resolve()
                if ROOT not in path.parents:
                    raise GoFailure("chi_package_module_missing")
            print(json.dumps({"status": "identity_verified", "identity_sha256": identity,
                              "identity": identity_detail, "official_reward": None}, sort_keys=True))
            return 0
        if args.mode == "reconcile-provider":
            from go_chi_journal import reconcile_provider_timeout
            if (args.history_mode != "external" or args.local_q_root is not None
                    or args.output_root is None or args.provider_record is None
                    or args.provider_record_sha256 is None or args.target_run is None
                    or args.target_round is None or args.expected_request_sha256 is None
                    or args.expected_accounting_sha256 is None or args.acknowledgement_reason is None):
                raise GoFailure("chi_reconcile_inputs_required")
            if args.expected_old_identity is not None and args.expected_old_identity != identity:
                raise GoFailure("chi_reconcile_identity_mismatch")
            result = reconcile_provider_timeout(
                _path(args.output_root, exists=True), identity=identity,
                accounting_sha256=args.expected_accounting_sha256, run=args.target_run,
                round_number=args.target_round, request_sha256=args.expected_request_sha256,
                provider_path=args.provider_record, provider_sha256=args.provider_record_sha256,
                reason=args.acknowledgement_reason)
            print(json.dumps({**result, "official_reward": None}, sort_keys=True))
            return 0
        if args.mode in {"audit-history", "rebind-history", "inspect-history", "acknowledge-unsettled"}:
            from go_chi_journal import audit_or_rebind, inspect_history, acknowledge_unsettled
            if args.history_mode != "local" or args.local_q_root is None or args.output_root is None:
                raise GoFailure("chi_local_history_required")
            qroot = _path(args.local_q_root, exists=True)
            root = _path(args.output_root, exists=True)
            if root != qroot / "chi-evaluation": raise GoFailure("chi_local_history_path_invalid")
            q = acquire_existing_history(qroot)
            if args.mode == 'acknowledge-unsettled':
                if args.provider_record is None or args.provider_record_sha256 is None:
                    raise GoFailure('chi_provider_record_invalid')
                result = acknowledge_unsettled(root, identity=args.expected_old_identity,
                    accounting_sha256=args.expected_accounting_sha256, run=args.target_run, round_number=args.target_round,
                    request_sha256=args.expected_request_sha256, provider_path=args.provider_record,
                    provider_sha256=args.provider_record_sha256, reason=args.acknowledgement_reason)
            elif args.mode == 'inspect-history':
                result = inspect_history(root, args.expected_old_identity, args.expected_accounting_sha256)
                if (args.provider_record is None) != (args.provider_record_sha256 is None):
                    raise GoFailure('chi_provider_record_invalid')
                if args.provider_record is not None:
                    from go_chi_inspect import inspect_provider
                    result['provider_record'] = inspect_provider(args.provider_record, args.provider_record_sha256,
                                                                result.get('pending_request'))
            else:
                if args.provider_record is not None or args.provider_record_sha256 is not None:
                    raise GoFailure('chi_provider_record_invalid')
                result = audit_or_rebind(root, args.expected_old_identity, args.expected_accounting_sha256,
                                         identity if args.mode == "rebind-history" else None, args.migration_reason)
            print(json.dumps({**result, "official_reward": None}, sort_keys=True))
            return 0
        if not all((args.evaluation_id, args.task_id, args.attempt_id, args.run_id, args.output_root,
                    args.logs_dir, args.history_mode)):
            raise GoFailure("chi_identity_and_paths_required")
        if args.mode == "coding-b" and (args.task_id != "synthetic-coding-b" or args.role or args.instruction_file or args.mcp_url):
            raise GoFailure("chi_b_contract_invalid")
        if args.mode == "live" and not all((args.role, args.instruction_file, args.mcp_url)):
            raise GoFailure("chi_launch_inputs_required")
        output_root, logs_dir, bundle = _path(args.output_root), _path(args.logs_dir), _path(ROOT, exists=True)
        if (not _disjoint(output_root, bundle) or not _disjoint(logs_dir, bundle)
                or not _disjoint(logs_dir, output_root) or logs_dir.exists() or not logs_dir.parent.is_dir()):
            raise GoFailure("chi_output_path_invalid")
        instruction_path = instruction = None
        launch = {"kind": "coding_b", "instruction_sha256": hashlib.sha256(INSTRUCTION.encode()).hexdigest(), "fee_policy": FEE_POLICY}
        if args.mode == "live":
            instruction_path, instruction = _instruction(args.instruction_file)
            if not _disjoint(instruction_path, output_root) or not _disjoint(instruction_path, logs_dir) or not _disjoint(instruction_path, bundle):
                raise GoFailure("chi_launch_path_overlap")
            _url(args.mcp_url)
            workspace = _path(args.workspace_root, exists=True)
            handbook = _path(args.handbook_root, exists=True)
            if (workspace != Path("/logs/artifacts/workspaces")
                    or handbook != Path("/workspace/skills/managed-care-operations-handbook")
                    or not workspace.is_dir() or not handbook.is_dir()):
                raise GoFailure("chi_resource_root_invalid")
            if any(not _disjoint(target, resource) for target in (output_root, logs_dir)
                   for resource in (workspace, handbook)):
                raise GoFailure("chi_launch_path_overlap")
            allowed_refs = {Path("/input/tool_reference.md"),
                            Path("/opt/healthverse-task-assets/tool_reference.md"),
                            Path("/opt/chi-bench-task-assets/tool_reference.md")}
            if not args.tool_reference:
                raise GoFailure("chi_reference_required")
            for reference in args.tool_reference:
                ref = _path(reference, exists=True)
                if (ref not in allowed_refs or not ref.is_file() or any(part.lower() in {"fixture", "fixtures", "hidden", "private", "verifier"}
                                              for part in ref.parts)
                        or any(not _disjoint(target, ref) for target in (output_root, logs_dir))):
                    raise GoFailure("chi_reference_invalid")
            references = {str(path): hashlib.sha256(_read_regular_bounded(_path(path, exists=True), 16 * 1024 * 1024,
                            "chi_reference_invalid")).hexdigest() for path in args.tool_reference}
            launch = {"kind": "chi", "role": args.role, "fee_policy": FEE_POLICY,
                      "instruction_sha256": hashlib.sha256(instruction.encode()).hexdigest(),
                      "mcp_url_sha256": hashlib.sha256(args.mcp_url.encode()).hexdigest(),
                      "tool_references_sha256": references, "handbook_sha256": _handbook_digest(handbook)}
            if args.output_recovery is not None:
                launch['output_recovery'] = args.output_recovery
            if development is not None and args.role == 'cm':
                launch['aux_contract'] = 'patient-simulator-v1'
        if args.history_mode == "local":
            if args.local_q_root is None:
                raise GoFailure("chi_local_history_required")
            qroot = _path(args.local_q_root, exists=True)
            # One deterministic CHI namespace beneath the existing Q root:
            # changing an output label cannot bypass a prior CHI pending claim.
            if output_root != qroot / "chi-evaluation" or not _disjoint(qroot, logs_dir):
                raise GoFailure("chi_local_history_path_invalid")
            q = acquire_existing_history(qroot)
        elif args.local_q_root is not None:
            raise GoFailure("chi_external_history_invalid")
        journal = ChiJournal(output_root, identity=identity, evaluation=args.evaluation_id, task=args.task_id,
                             attempt=args.attempt_id, run=args.run_id,
                             kind="coding_b" if args.mode == "coding-b" else "chi", require_b=args.mode == "live",
                             launch=launch)
        secret = os.environ.get("OPENCODE_API_KEY")
        if type(secret) is not str or not secret.strip():
            raise GoFailure("chi_credential_missing")
        if args.mode == "coding-b":
            logs_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
            text = asyncio.run(_run_b(journal, secret))
            (logs_dir / "run_output.txt").write_text(text, encoding="utf-8")
            (logs_dir / "run_result.json").write_text(json.dumps({"status": "complete", "official_reward": None,
                "run_id": args.run_id, "requests": len(journal.run["requests"]),
                "usage": journal.usage_totals()}, sort_keys=True), encoding="utf-8")
            (logs_dir / "run_log.txt").write_text(json.dumps({"status": "complete", "safe_error_code": None,
                "provider_requests": len(journal.run["requests"]), "tool_events": len(journal.run["tool_events"]),
                "official_reward": None}, sort_keys=True), encoding="utf-8")
        else:
            import httpx
            from go_chi_runtime import run_chi
            async def execute():
                kwargs = dict(role=args.role, instruction=instruction, mcp_url=args.mcp_url,
                    instruction_path=instruction_path, logs_dir=logs_dir, workspace_root=args.workspace_root,
                    handbook_root=args.handbook_root, tool_references=args.tool_reference,
                    lower=httpx.AsyncHTTPTransport(retries=0, verify=True),
                    capabilities="f0-f3-v1")
                if development is None:
                    return await run_chi(journal, secret, **kwargs)
                return await development(journal, secret, run_chi, kwargs)
            text = asyncio.run(execute())
        journal.finish("complete")
        if args.mode == "coding-b":
            journal.prepare_b_receipt()
            b_receipt = copy.deepcopy(journal.run)
        output = {"status": "complete", "run_id": args.run_id, "identity_sha256": identity,
                  "usage": journal.usage_totals(), "official_reward": None}
        code = 0
    except BaseException as exc:
        code = 1
        error = getattr(exc, "code", "chi_entry_failed")
        if type(error) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", error):
            error = "chi_entry_failed"
        output = {"status": "incomplete" if journal is not None else "blocked", "safe_error_code": error, "official_reward": None}
        if journal is not None:
            try: journal.finish("failed", error)
            except Exception: output["safe_error_code"] = "chi_persistence_failed"
            try:
                if "logs_dir" in locals() and logs_dir.is_dir():
                    (logs_dir / "run_error.json").write_text(json.dumps(output, sort_keys=True), encoding="utf-8")
                    (logs_dir / "run_log.txt").write_text(json.dumps({"status": "incomplete", "safe_error_code": error,
                        "provider_requests": len(journal.run["requests"]), "tool_events": len(journal.run["tool_events"]),
                        "official_reward": None}, sort_keys=True), encoding="utf-8")
            except Exception:
                output["safe_error_code"] = "chi_log_persistence_failed"
        if isinstance(exc, KeyboardInterrupt): output["safe_error_code"] = "chi_interrupted"
    finally:
        if journal is not None:
            try: journal.close()
            except Exception: output, code = {"status": "incomplete", "safe_error_code": "chi_cleanup_failed", "official_reward": None}, 1
        if q is not None:
            try: q.close()
            except Exception: output, code = {"status": "incomplete", "safe_error_code": "chi_cleanup_failed", "official_reward": None}, 1
    if code == 0 and b_receipt is not None:
        try:
            publish_b_receipt(output_root, identity, b_receipt)
        except Exception:
            output, code = {"status": "incomplete", "safe_error_code": "chi_b_receipt_persistence_failed", "official_reward": None}, 1
    print(json.dumps(output, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
