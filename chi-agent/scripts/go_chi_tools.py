"""Bounded role-specific local tool primitives for Go CHI runtime integration."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

from opencode_go_provider import GoFailure
from go_chi_resources import workspace_path
from evaluation_bundle import _check_components, BundleFailure
from go_chi_guidance import guidance as role_guidance
from go_chi_search import SearchRefusal, search as bounded_search
from go_chi_state import StateRefusal
from payer_evidence import CASE_ID, EvidenceRegistry
from pdf_resource_reader import read_allowed_file

EVIDENCE_SHADOW_MODES = {None, "off", "shadow"}
CAPABILITIES = {None, "f0-f3-v1"}
OBSERVED_LOCAL = {"local-fs-read", "local-fs-list", "local-fs-search",
                  "local-fs-write", "local-fs-edit", "local-read-patient-observation"}


def local_tools(*, role, workspace_root, instruction_path, tool_references, handbook_root,
                journal, binding, guard_getter, client_getter, confirmation_context,
                exchanges, dispatch_lock, instruction=None, evidence_shadow=None,
                state=None, capabilities=None):
    from agents.tool import FunctionTool
    if role not in {"provider", "payer", "cm"} or (role == "provider" and binding is None):
        raise GoFailure("chi_local_role_invalid")
    if capabilities not in CAPABILITIES:
        raise GoFailure("chi_capabilities_invalid")
    if capabilities == "f0-f3-v1" and state is None:
        raise GoFailure("chi_state_missing")
    if evidence_shadow not in EVIDENCE_SHADOW_MODES:
        raise GoFailure("chi_evidence_shadow_invalid")
    if evidence_shadow == "off":
        evidence_shadow = None
    if evidence_shadow == "shadow" and role != "payer":
        raise GoFailure("chi_evidence_shadow_role_invalid")
    if evidence_shadow == "shadow" and (type(instruction) is not str or not instruction):
        raise GoFailure("chi_evidence_shadow_input_invalid")
    workspace_root = Path(workspace_root)
    instruction_path = Path(instruction_path)
    handbook_root = Path(handbook_root)
    fixed = {str(instruction_path), *(str(Path(path)) for path in tool_references)}

    def classify_source(tool, arguments, result):
        """Derive case/shared scope from the existing path allowlist only."""
        try:
            args = json.loads(arguments) if type(arguments) is str else {}
        except Exception:
            args = {}
        if type(args) is not dict:
            args = {}
        declared = args.get("case_id")
        if type(declared) is not str or not CASE_ID.fullmatch(declared):
            declared = None
        scope = None
        if tool in {"local-fs-read", "local-fs-list", "local-fs-search",
                    "local-fs-write", "local-fs-edit"} and type(args.get("path")) is str:
            value = args["path"]
            directory = tool in {"local-fs-list", "local-fs-search"}
            path = workspace_path(workspace_root, value, role, directory=directory)
            if path is not None:
                try:
                    relative = path.relative_to(workspace_root)
                except ValueError:
                    relative = None
                if relative is not None and len(relative.parts) >= (2 if directory else 3):
                    scope = "case:" + relative.parts[0]
            else:
                try:
                    candidate = _check_components(Path(value), "chi_local_path_invalid",
                                                  final_may_be_missing=False)
                    handbook = _check_components(handbook_root, "chi_local_path_invalid",
                                                 final_may_be_missing=False)
                    if candidate == handbook or handbook in candidate.parents:
                        scope = "shared_public"
                    elif str(candidate) in fixed:
                        scope = "shared_public"
                except (BundleFailure, ValueError):
                    scope = None
        if declared is not None:
            if scope is not None and scope != "shared_public" and scope != "case:" + declared:
                return "conflict"
            if scope in (None, "shared_public"):
                scope = "case:" + declared
        return scope or "unattributed"

    registry = (EvidenceRegistry(instruction=instruction, classify=classify_source)
                if evidence_shadow == "shadow" else None)

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
            try:
                parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            except OSError:
                return "ERROR: workspace parent unavailable"
            try:
                root = workspace_root.resolve(strict=True)
                if root != parent.resolve(strict=True) and root not in parent.resolve(strict=True).parents:
                    return "ERROR: workspace parent unavailable"
            except OSError:
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
        guard = guard_getter()
        if guard is not None:
            pending = [record for record in guard.contract.records
                       if record["result"] is None and record["name"] != "local-claim_done"]
            if pending:
                return "REFUSED: completion_batch_pending:" + pending[0]["id"]
        if state is not None:
            outcome = state.record_claim()
            if outcome["status"] != "recorded":
                return "REFUSED: " + outcome["reason"]
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

    def tool_event(call_id):
        final = None
        for event in journal.run["tool_events"]:
            if event.get("call_id") == call_id:
                final = event.get("event")
        return final

    def shadow_error(code):
        return json.dumps({"mode": "shadow", "error": code}, ensure_ascii=False, sort_keys=True)

    def require_shadow():
        if registry is None:
            raise GoFailure("chi_evidence_shadow_invalid")

    async def evidence_sources(args):
        require_shadow()
        if type(args) is not dict or args:
            return shadow_error("arguments_invalid")
        registry.register_observations(exchanges, tool_event)
        return json.dumps(registry.listing(), ensure_ascii=False, sort_keys=True, allow_nan=False)

    async def evidence_excerpt(args):
        require_shadow()
        if type(args) is not dict or set(args) != {"source_id", "start_char", "end_char"}:
            return shadow_error("arguments_invalid")
        registry.register_observations(exchanges, tool_event)
        return json.dumps(registry.excerpt(args["source_id"], args["start_char"], args["end_char"]),
                          ensure_ascii=False, sort_keys=True, allow_nan=False)

    async def evidence_check(args):
        require_shadow()
        if type(args) is not dict or set(args) != {"checklist"}:
            return shadow_error("checklist_malformed")
        registry.register_observations(exchanges, tool_event)
        try:
            payload_bytes = len(json.dumps(args["checklist"], ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":"), allow_nan=False).encode("utf-8"))
            result = registry.validate(args["checklist"], payload_bytes=payload_bytes)
            return json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except Exception:
            return shadow_error("checklist_malformed")

    def require_state():
        if state is None:
            raise GoFailure("chi_state_missing")

    async def task_state(_args):
        require_state()
        return json.dumps(state.summary(), ensure_ascii=False, sort_keys=True, allow_nan=False)

    async def state_update(args):
        require_state()
        try:
            result = state.propose(args)
        except StateRefusal as exc:
            return "REFUSED: " + exc.code
        return json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)

    async def completion_check(_args):
        require_state()
        return json.dumps(state.completion_report(), ensure_ascii=False, sort_keys=True, allow_nan=False)

    async def role_guidance_tool(args):
        if type(args) is not dict or args:
            return "REFUSED: chi_guidance_arguments_invalid"
        try:
            value = role_guidance(role, state.summary() if state is not None else None)
        except ValueError:
            raise GoFailure("chi_guidance_role_invalid") from None
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)

    def search_loader(path):
        try:
            with path.open("rb") as handle:
                header = handle.read(5)
        except OSError:
            return None
        if path.suffix.lower() == ".pdf" or header == b"%PDF-":
            value = read_allowed_file(path, None, None, pdf_enabled=True)
            return None if value.startswith("ERROR:") else value
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            return None

    async def fs_search(args):
        require_state()
        if (type(args) is not dict or set(args) - {"path", "query", "max_results", "case_sensitive"}
                or "path" not in args or "query" not in args):
            return "REFUSED: search_arguments_invalid"
        path = allowed_read(args["path"], directory=True) or allowed_read(args["path"])
        if path is None or path.is_symlink() or not (path.is_file() or path.is_dir()):
            return "REFUSED: search_path_outside_allowlist"
        workspace_target = (workspace_path(workspace_root, args["path"], role, directory=True)
                            or workspace_path(workspace_root, args["path"], role))
        if workspace_target is not None:
            case_id = workspace_target.relative_to(workspace_root).parts[0]
            target_case = state.data["target"]["case_id"]
            if target_case is None or case_id != target_case:
                return "REFUSED: search_path_outside_allowlist"
        try:
            value = bounded_search([path], args["query"],
                                   max_results=args.get("max_results", 8),
                                   case_sensitive=args.get("case_sensitive", False),
                                   read_text=search_loader, single_file=path.is_file())
        except SearchRefusal as exc:
            if exc.code == "search_unreadable":
                return "ERROR: search_unreadable"
            return "REFUSED: " + exc.code
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    def schema(properties, required):
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    text_item = {"type": "object", "properties": {"text": {"type": "string"}},
                 "required": ["text"], "additionalProperties": False}
    source_item = {"type": "object",
                   "properties": {"text": {"type": "string"}, "source_call_id": {"type": "string"}},
                   "required": ["text", "source_call_id"], "additionalProperties": False}
    state_update_schema = schema({
        "facts": {"type": "array", "items": source_item},
        "plans": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "status": {"type": "string", "enum": ["open", "resolved"]},
            "source_call_id": {"type": "string"}},
            "required": ["text", "status"], "additionalProperties": False}},
        "target": {"type": "object", "properties": {"case_id": {"type": "string"},
                                                    "patient_id": {"type": "string"}},
                   "additionalProperties": False},
        "latest_business_status": source_item,
        "next_candidates": {"type": "array", "items": {"type": "string"}},
        "resolve_unknown": {"type": "array", "items": {"type": "object", "properties": {
            "unknown_id": {"type": "string"}, "source_call_id": {"type": "string"},
            "note": {"type": "string"}},
            "required": ["unknown_id", "source_call_id", "note"], "additionalProperties": False}},
    }, [])
    search_schema = schema({
        "path": {"type": "string"},
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
        "case_sensitive": {"type": "boolean"},
    }, ["path", "query"])
    defs = [
        ("local-fs-read", "Read an allowlisted task, handbook or role workspace file.", schema({"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 1}, "limit": {"type": "integer", "minimum": 1}}, ["path"]), read_file),
        ("local-fs-list", "List an allowlisted role workspace or handbook directory.", schema({"path": {"type": "string"}}, ["path"]), list_files),
        ("local-fs-write", "Write a file inside the permitted role workspace. The path must be an absolute path of the form "
         "'<workspace>/<case_id>/<role>/<file>' or '<workspace>/<case_id>/shared/<file>', where <role> is exactly "
         "provider, payer or cm; missing parent directories are created.", schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]), write_file),
        ("local-fs-edit", "Edit a file inside the permitted role workspace.", schema({"path": {"type": "string"}, "old_string": {"type": "string", "minLength": 1}, "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}}, ["path", "old_string", "new_string"]), edit_file),
        ("local-claim_done", "Mark the task as complete after finishing the work.", empty, claim),
    ]
    if binding is not None:
        from patient_identity_binding import CONFIRM_DESCRIPTION, READ_DESCRIPTION
        defs.extend([
            ("local-read-patient-observation", READ_DESCRIPTION, schema({"patient_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}}, ["patient_id", "offset"]), observation),
            ("local-confirm-patient", CONFIRM_DESCRIPTION, schema({"patient_id": {"type": "string"}, "instruction_quote": {"type": "string", "minLength": 1}, "chart_quote": {"type": "string", "minLength": 1}}, ["patient_id", "instruction_quote", "chart_quote"]), confirm),
        ])
    if capabilities == "f0-f3-v1":
        defs.extend([
            ("local-task-state",
             "Read this run's bounded task state: target, observed sources, facts, plans, gaps, open unknown writes, latest business status and next candidates. Read it before planning or after a surprising tool result.",
             empty, task_state),
            ("local-state-update",
             "Submit a sourced task-state update. Facts and latest business status must cite a call_id already observed in this run. The program fills source versions and rejects stale, wrong-case, unobserved or binding-changing updates. It cannot mark an unknown write as success or failure.",
             state_update_schema, state_update),
            ("local-completion-check",
             "Report mechanical completion evidence: target, latest business status, last mutation, open unknowns, claim and whether a later readback is missing. It does not claim, approve, or produce a clinical/official verdict.",
             empty, completion_check),
            ("local-role-guidance",
             "Return the versioned role stage guide with legal branches, preconditions, readbacks and stop conditions. It contains no task answers or expected outcomes; decide from public observations.",
             empty, role_guidance_tool),
            ("local-fs-search",
             "Search an allowlisted public directory or fixed reference file for a literal string. Returns bounded line hits with path, line, byte offset, file hash and truncation flags. Re-read the original context with local-fs-read before citing it.",
             search_schema, fs_search),
        ])
    if evidence_shadow == "shadow":
        defs.extend([
            ("local-evidence-sources",
             "Shadow-only record for payer development. List opaque ids for public text this run actually sent to the main model; returns metadata, never text. It cannot approve, block, or choose an action.",
             {"type": "object", "properties": {}, "additionalProperties": True}, evidence_sources),
            ("local-evidence-excerpt",
             "Shadow-only record for payer development. Read a bounded character window from a registered source. Indices are 0-based and end-exclusive. It cannot approve, block, or choose an action.",
             {"type": "object", "properties": {"source_id": {"description": "Opaque id such as src-0001."}, "start_char": {"description": "0-based character index."}, "end_char": {"description": "Exclusive character index."}}, "additionalProperties": True}, evidence_excerpt),
            ("local-evidence-check",
             "Shadow-only record for payer development. Validate citation boundaries for a bounded checklist; returns reference_validation and semantic_assessment=not_performed. It does not judge clinical meaning and cannot approve, block, or choose an action.",
             {"type": "object", "properties": {"checklist": {"description": "Object with case_id, proposed_action, claims, unresolved."}}, "additionalProperties": True}, evidence_check),
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
                fatal = getattr(guard, 'fatal_getter', lambda: None)()
                if fatal:
                    raise GoFailure(fatal)
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
                if state is not None:
                    stagnant = state.stagnation_block_reason(name, "local", args)
                    if stagnant is not None:
                        output = "REFUSED: " + stagnant
                        journal.refuse_tool(selected["id"], name, args, output, secrets=(guard.secret, guard.session))
                        guard.contract.record_result(selected["id"], output)
                        return output
                    blocked = state.block_mutation(name, "local", args)
                    if blocked is not None:
                        output = "REFUSED: " + blocked
                        journal.refuse_tool(selected["id"], name, args, output, secrets=(guard.secret, guard.session))
                        guard.contract.record_result(selected["id"], output)
                        return output
                warning = (state.stagnation_warning(name, "local", args)
                           if state is not None else None)
                journal.start_tool(selected["id"], name, args)
                try:
                    output = await callback(args)
                    if warning:
                        output = output + "\n" + warning
                    guard.contract.record_result(selected["id"], output)
                    journal.record_tool(selected["id"], name, output,
                                        event="refused" if output.startswith("REFUSED:") else "returned",
                                        secrets=(guard.secret, guard.session))
                    if state is not None and name in OBSERVED_LOCAL:
                        event = ("refused" if output.startswith("REFUSED:") else
                                 "returned_error" if output.startswith("ERROR:") else "returned")
                        scope = (classify_source(name, json.dumps(args, ensure_ascii=False), output)
                                 if name in {"local-fs-read", "local-fs-list", "local-fs-search",
                                             "local-fs-write", "local-fs-edit"}
                                 else state.scope_for_arguments(args))
                        run_doc = getattr(journal, "run", None)
                        rounds = len(run_doc.get("requests", [])) if isinstance(run_doc, dict) else 0
                        state.observe(call_id=selected["id"], tool=name, kind="local", arguments=args,
                                      result=output, event=event, round_number=rounds, scope=scope)
                    return output
                except BaseException as exc:
                    code = ("chi_tool_cancelled" if isinstance(exc, __import__("asyncio").CancelledError) else
                            exc.code if isinstance(exc, GoFailure) else "chi_tool_execution_failed")
                    try: journal.record_tool(selected["id"], name, code, event="failed",
                                             secrets=(guard.secret, guard.session))
                    except Exception: pass
                    if state is not None and name in OBSERVED_LOCAL:
                        try:
                            state.observe(call_id=selected["id"], tool=name, kind="local", arguments=args,
                                          result=code, event="failed",
                                          round_number=len(getattr(journal, "run", {}).get("requests", []))
                                          if isinstance(getattr(journal, "run", None), dict) else 0,
                                          scope=(classify_source(name, json.dumps(args, ensure_ascii=False), code)
                                                 if name in {"local-fs-read", "local-fs-list", "local-fs-search",
                                                             "local-fs-write", "local-fs-edit"}
                                                 else state.scope_for_arguments(args)))
                        except Exception:
                            pass
                    if binding is not None and name in {"local-fs-write", "local-fs-edit", "local-confirm-patient"}:
                        binding.poisoned = True
                    raise
        result.append(FunctionTool(name=name, description=description, params_json_schema=params,
                                   on_invoke_tool=tracked, strict_json_schema=False))
    return result
