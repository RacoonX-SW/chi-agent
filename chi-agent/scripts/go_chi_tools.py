"""Bounded role-specific local tool primitives for Go CHI runtime integration."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

from opencode_go_provider import GoFailure
from go_chi_resources import workspace_path
from evaluation_bundle import _check_components, BundleFailure
from pdf_resource_reader import read_allowed_file


def local_tools(*, role, workspace_root, instruction_path, tool_references, handbook_root,
                journal, binding, guard_getter, client_getter, confirmation_context,
                exchanges, dispatch_lock):
    from agents.tool import FunctionTool
    if role not in {"provider", "payer", "cm"} or (role == "provider" and binding is None):
        raise GoFailure("chi_local_role_invalid")
    workspace_root = Path(workspace_root)
    instruction_path = Path(instruction_path)
    handbook_root = Path(handbook_root)
    fixed = {str(instruction_path), *(str(Path(path)) for path in tool_references)}

    def allowed_read(value, *, directory=False):
        if type(value) is not str:
            return None
        path = workspace_path(workspace_root, value, role, directory=directory)
        if path is not None:
            return path
        try:
            candidate = _check_components(Path(value), "chi_local_path_invalid", final_may_be_missing=False)
            handbook = _check_components(handbook_root, "chi_local_path_invalid", final_may_be_missing=False)
            if candidate == handbook or handbook in candidate.parents:
                relative = candidate.relative_to(handbook)
                if any(part.startswith(".") or part.lower() in {"fixture", "fixtures", "verifier", "judge", "hidden", "private", "expectations"}
                       for part in relative.parts):
                    return None
                return candidate
            if not directory and str(candidate) in fixed:
                return candidate
        except (BundleFailure, ValueError):
            pass
        return None

    def writable(value):
        path = workspace_path(workspace_root, value, role)
        if path is None:
            return None
        if role == "provider":
            case = path.relative_to(workspace_root).parts[0]
            if binding.bound is None or binding.poisoned or binding.cases.get(case) != binding.bound:
                return None
        return path

    async def read_file(args):
        path = allowed_read(args.get("path"))
        if path is None or not path.is_file() or path.is_symlink():
            return "ERROR: file is outside the role allowlist or unavailable"
        return read_allowed_file(path, args.get("offset"), args.get("limit"), pdf_enabled=True)

    async def list_files(args):
        path = allowed_read(args.get("path"), directory=True)
        if path is None or not path.is_dir() or path.is_symlink():
            return "ERROR: directory is outside the role allowlist or unavailable"
        return "\n".join(sorted(item.name for item in path.iterdir()
                                if not item.name.startswith(".") and item.name.lower() not in
                                {"fixture", "fixtures", "verifier", "judge", "hidden", "private", "expectations"}
                                and not item.is_symlink() and (item.is_file() or item.is_dir())))

    async def write_file(args):
        path = writable(args.get("path"))
        if path is None:
            return "REFUSED: workspace_case_unverified_or_role_invalid"
        parent = path.parent
        if not parent.is_dir():
            return "ERROR: workspace parent unavailable"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(args["content"])
        except OSError:
            raise GoFailure("chi_local_write_failed") from None
        return "workspace file written"

    async def edit_file(args):
        from evaluation_bundle import _read_regular_bounded
        path = writable(args.get("path"))
        if path is None:
            return "REFUSED: workspace_case_unverified_or_role_invalid"
        try:
            old = _read_regular_bounded(path, 1024 * 1024, "chi_local_edit_invalid").decode("utf-8")
        except Exception:
            return "ERROR: workspace file unavailable"
        if not args["old_string"] or args["old_string"] not in old:
            return "ERROR: old_string not found"
        new = old.replace(args["old_string"], args["new_string"], -1 if args.get("replace_all", False) else 1)
        return await write_file({"path": str(path), "content": new})

    async def claim(_args):
        journal.record_claim()
        return "task marked as done"

    async def observation(args):
        from patient_identity_binding import Refusal
        try:
            return binding.read_observation(args["patient_id"], args["offset"])
        except Refusal as exc:
            return "REFUSED: " + str(exc)

    async def confirm(args):
        from patient_identity_binding import PROMPT, PROMPT_VERSION, MAX_CONFIRM_INPUT, CONFIRM_MAX_OUTPUT_TOKENS, Refusal
        try:
            evidence = binding.confirmation_input(args["patient_id"], exchanges)
            if (not args["instruction_quote"].strip() or args["instruction_quote"] not in binding.instruction
                    or not args["chart_quote"].strip() or args["chart_quote"] not in binding.charts[args["patient_id"]]["text"]):
                raise Refusal("selection_evidence_unverified")
        except Refusal as exc:
            return "REFUSED: " + str(exc)
        evidence = json.dumps({"selection": args, "public_observations": json.loads(evidence)}, ensure_ascii=False)
        if len(evidence.encode()) > MAX_CONFIRM_INPUT:
            return "REFUSED: confirmation_input_too_large"
        binding.confirmations += 1
        binding.event("confirmation_attempt", attempt=binding.confirmations, prompt_version=PROMPT_VERSION,
                      prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
                      evidence_sha256=hashlib.sha256(evidence.encode()).hexdigest())
        token = confirmation_context.set((PROMPT, evidence))
        try:
            response = await client_getter().chat.completions.create(
                model="deepseek-v4.1-flash", messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": evidence}],
                max_tokens=CONFIRM_MAX_OUTPUT_TOKENS, response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "high"})
        finally:
            confirmation_context.reset(token)
        choice = response.choices[0]
        content = choice.message.content
        if choice.finish_reason == "length":
            result = {"status": "invalid", "reason": "confirmation_output_truncated"}
            binding.event("confirmation_result", attempt=binding.confirmations, result=result)
            return json.dumps(result, ensure_ascii=False)
        if choice.finish_reason != "stop" or not isinstance(content, str) or not content.strip():
            return json.dumps({"status": "invalid", "reason": "confirmation_format_invalid"})
        result = binding.assess(args["patient_id"], content)
        binding.event("confirmation_result", attempt=binding.confirmations, result=result)
        return json.dumps(result, ensure_ascii=False)

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    def schema(properties, required):
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    defs = [
        ("local-fs-read", "Read an allowlisted task, handbook or role workspace file.", schema({"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1}}, ["path"]), read_file),
        ("local-fs-list", "List an allowlisted role workspace or handbook directory.", schema({"path": {"type": "string"}}, ["path"]), list_files),
        ("local-fs-write", "Write a file inside the permitted role workspace.", schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), write_file),
        ("local-fs-edit", "Edit a file inside the permitted role workspace.", schema({"path": {"type": "string"}, "old_string": {"type": "string", "minLength": 1}, "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}}, ["path", "old_string", "new_string"]), edit_file),
        ("local-claim_done", "Mark the task as complete after finishing the work.", empty, claim),
    ]
    if binding is not None:
        from patient_identity_binding import CONFIRM_DESCRIPTION, READ_DESCRIPTION
        defs.extend([
            ("local-read-patient-observation", READ_DESCRIPTION, schema({"patient_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}}, ["patient_id", "offset"]), observation),
            ("local-confirm-patient", CONFIRM_DESCRIPTION, schema({"patient_id": {"type": "string"}, "instruction_quote": {"type": "string", "minLength": 1}, "chart_quote": {"type": "string", "minLength": 1}}, ["patient_id", "instruction_quote", "chart_quote"]), confirm),
        ])
    result = []
    for name, description, params, callback in defs:
        async def tracked(_context, payload, *, name=name, callback=callback):
            guard = guard_getter()
            if guard is None:
                raise GoFailure("chi_local_guard_missing")
            try:
                args = json.loads(payload)
            except Exception:
                raise GoFailure("chi_local_arguments_invalid") from None
            async with dispatch_lock:
                pending = [item for item in guard.contract.records
                           if item["name"] == name and item["arguments"] == args and item["result"] is None]
                if not pending:
                    raise GoFailure("chi_local_dispatch_unvalidated")
                selected = pending[0]
                reason = guard.contract.refusals.get(selected["id"])
                if reason is None and binding is not None and name in {"local-fs-write", "local-fs-edit"}:
                    reason = binding.batch_refusals.get(selected["id"])
                if reason is not None:
                    output = "REFUSED: " + reason
                    journal.refuse_tool(selected["id"], name, args, output, secrets=(guard.secret, guard.session))
                    guard.contract.record_result(selected["id"], output)
                    return output
                journal.start_tool(selected["id"], name, args)
                try:
                    output = await callback(args)
                    guard.contract.record_result(selected["id"], output)
                    journal.record_tool(selected["id"], name, output,
                                        event="refused" if output.startswith("REFUSED:") else "returned",
                                        secrets=(guard.secret, guard.session))
                    return output
                except BaseException as exc:
                    code = ("chi_tool_cancelled" if isinstance(exc, __import__("asyncio").CancelledError) else
                            exc.code if isinstance(exc, GoFailure) else "chi_tool_execution_failed")
                    try: journal.record_tool(selected["id"], name, code, event="failed",
                                             secrets=(guard.secret, guard.session))
                    except Exception: pass
                    if binding is not None and name in {"local-fs-write", "local-fs-edit", "local-confirm-patient"}:
                        binding.poisoned = True
                    raise
        result.append(FunctionTool(name=name, description=description, params_json_schema=params,
                                   on_invoke_tool=tracked, strict_json_schema=False))
    return result
