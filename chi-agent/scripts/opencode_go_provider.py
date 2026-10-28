#!/usr/bin/env python3
"""OpenCode Go provider and fixed synthetic coding probe; no CHI task entry."""
from __future__ import annotations

import argparse
import ast
import asyncio
import fcntl
import hashlib
import importlib.metadata
import json
import logging
import math
import os
import re
import stat
import tempfile
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles/opencode-go-deepseek.json"
DEFAULT_ROOT = ROOT / "runs/opencode-go-development"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
CALL_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
PROFILE = {"schema": "chi-opencode-go-profile-v1", "profile_id": "opencode-go-deepseek-v4.1-flash-v1",
           "base_url": "https://opencode.ai/inference/go/openai/v1", "model": "deepseek-v4.1-flash",
           "key_env": "OPENCODE_API_KEY", "user_agent": "chi-agent", "session_header": "x-opencode-session",
           "max_requests": 6, "max_output_tokens": 1024, "documented_context_tokens": 1048576,
           "context_evidence": "documentation_only_not_measured", "thinking": {"type": "enabled"},
           "reasoning_effort": "high", "currency": "USD", "automatic_retries": 0}
INSTRUCTION = ("Fix a small Python function that should add two integers. Call inspect_code first, then call "
               "verify_patch with your corrected Python function. Finish with a short confirmation only after verification passes.")
SYSTEM = "You are a coding assistant. Follow the fixed synthetic coding task and use only the supplied tools."
INSPECT_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
VERIFY_SCHEMA = {"type": "object", "properties": {"code": {"type": "string", "maxLength": 512}},
                 "required": ["code"], "additionalProperties": False}
SCHEMAS = {"inspect_code": INSPECT_SCHEMA, "verify_patch": VERIFY_SCHEMA}
DESCRIPTIONS = {"inspect_code": "Inspect the synthetic buggy Python function.",
                "verify_patch": "Verify the corrected synthetic Python function."}

def _contains_secret(value, *secrets):
    if isinstance(value, str): return any(secret and secret in value for secret in secrets)
    if isinstance(value, dict): return any(_contains_secret(k, *secrets) or _contains_secret(v, *secrets) for k, v in value.items())
    if isinstance(value, list): return any(_contains_secret(v, *secrets) for v in value)
    return False


class GoFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path, limit: int = 1_000_000) -> bytes:
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise GoFailure("path_invalid")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise GoFailure("file_invalid")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise GoFailure("file_invalid")
    return data


def _object(path: Path) -> dict:
    try:
        value = json.loads(_read_regular(path, 32 * 1024 * 1024), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError
        return value
    except Exception:
        raise GoFailure("state_invalid") from None


def _atomic(path: Path, value: dict, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    if exclusive:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    else:
        fd, temporary = tempfile.mkstemp(prefix=".go-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise
    directory = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def load_profile() -> tuple[dict, str]:
    try:
        raw = _read_regular(PROFILE_PATH, 65536)
        value = json.loads(raw, object_pairs_hook=_unique)
        from b_provider_profile import _same_typed_value
        if not _same_typed_value(value, PROFILE):
            raise ValueError
        return value, _sha(raw)
    except Exception:
        raise GoFailure("go_profile_invalid") from None


def source_identity() -> dict:
    _, profile_hash = load_profile()
    paths = ("scripts/opencode_go_provider.py", "profiles/opencode-go-deepseek.json", "requirements-model.lock",
             "scripts/b_provider_profile.py", "scripts/b_provider_transport.py", "scripts/b_execution_policy.py",
             "scripts/model_runner_adapter.py", "scripts/b_model_adapter.py")
    try:
        sdk = {name: importlib.metadata.version(name) for name in ("openai-agents", "openai", "httpx")}
        if sdk != {"openai-agents": "0.13.6", "openai": "2.36.0", "httpx": "0.28.1"}:
            raise ValueError
        return {"profile_sha256": profile_hash,
                "files_sha256": {path: _sha(_read_regular(ROOT / path, 8 * 1024 * 1024)) for path in paths},
                "sdk": sdk}
    except Exception:
        raise GoFailure("go_identity_unavailable") from None


def _amount(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) not in (int, float, str) or (type(value) is float and not math.isfinite(value)):
        raise ValueError
    try: amount = Decimal(str(value))
    except InvalidOperation: raise ValueError from None
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
        raise ValueError
    return str(amount)


def _billing(usage: dict) -> tuple[dict, str | None]:
    details = usage.get("opencode")
    details = details if type(details) is dict else {}
    values = {}
    invalid = False
    for name, value in (("charged_usd", usage.get("cost")), ("list_cost_usd", details.get("list_cost")),
                        ("allowance_usd", details.get("allowance"))):
        try:
            if value is not None and type(value) not in (int, float): raise ValueError
            values[name] = _amount(value)
        except ValueError: values[name] = None; invalid = True
    if details.get("estimated") is True or ("estimated" in details and type(details["estimated"]) is not bool):
        values["charged_usd"] = None
        invalid = True
    source = details.get("billing_source")
    values["billing_source"] = (source if source in {"go", "go-plus", "free", "balance", "byok"} else "other") if type(source) is str else None
    if source is None:
        return values, "billing_details_unknown"
    if values["billing_source"] not in {"go", "go-plus"} or (values["charged_usd"] is not None and Decimal(values["charged_usd"]) != 0):
        return values, "billing_source_unexpected"
    if invalid or any(values[name] is None for name in ("charged_usd", "list_cost_usd", "allowance_usd")):
        return values, "billing_details_unknown"
    return values, None


class GoJournal:
    """One source-bound USD namespace; prior account history is not presumed zero."""
    def __init__(self, root: Path, run_id: str, identity: dict, *, maintenance: bool = False):
        if not ID_RE.fullmatch(run_id): raise GoFailure("run_id_invalid")
        from b_provider_transport import _reject_symlink_ancestors
        try:
            _reject_symlink_ancestors(root, "path_invalid")
            root.mkdir(parents=True, exist_ok=True)
            _reject_symlink_ancestors(root, "path_invalid")
            self.lock = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            if hasattr(self, "lock"): os.close(self.lock)
            raise GoFailure("go_journal_locked_or_invalid") from None
        self.root, self.run_id = root, run_id
        self.state_path, self.run_path = root / "accounting.json", root / "runs" / f"{run_id}.json"
        try:
            if (root / ".rebind-pending").exists() or (root / ".rebind-pending").is_symlink(): raise GoFailure("go_rebind_incomplete")
            if not self.state_path.exists():
                if maintenance: raise GoFailure("go_history_missing")
                if any(item.name != ".lock" for item in root.iterdir()): raise GoFailure("go_history_missing")
                state = {"schema": "chi-opencode-go-usd-v1", "identity": identity, "currency": "USD",
                         "account_prior_history": "unknown", "pending": None, "usage_complete": True,
                         "halted": None, "known_input_tokens": 0, "known_output_tokens": 0,
                         "charged_usd_known": "0", "list_cost_usd_known": "0", "allowance_usd_known": "0",
                         "charged_complete": True, "list_cost_complete": True, "allowance_complete": True}
                _atomic(self.state_path, state, exclusive=True)
            self.state = _object(self.state_path)
            self._validate(identity)
            if self.state["pending"] is not None or self.state["usage_complete"] is not True:
                raise GoFailure("go_usage_unknown")
            self._audit_runs()
            if self.state["halted"] is not None: raise GoFailure("go_billing_halted")
            if maintenance: return
            _reject_symlink_ancestors(self.run_path.parent, "path_invalid")
            if self.run_path.exists() or self.run_path.is_symlink(): raise GoFailure("run_id_exists")
            self.run = {"schema": "chi-opencode-go-probe-run-v1", "run_id": run_id, "identity": identity,
                        "status": "started", "requests": [], "tool_events": [], "official_reward": None}
            _atomic(self.run_path, self.run, exclusive=True)
        except BaseException:
            self.close()
            raise

    def _validate(self, identity: dict) -> None:
        s = self.state
        keys = {"schema", "identity", "currency", "account_prior_history", "pending", "usage_complete", "halted",
                "known_input_tokens", "known_output_tokens", "charged_usd_known", "list_cost_usd_known", "allowance_usd_known",
                "charged_complete", "list_cost_complete", "allowance_complete"}
        try:
            if (set(s) not in (keys, keys | {"source_transitions"}) or s["schema"] != "chi-opencode-go-usd-v1" or s["currency"] != "USD"
                    or s["identity"] != identity or s["account_prior_history"] != "unknown"
                    or type(s["usage_complete"]) is not bool or s["halted"] not in (None, "billing_source_unexpected", "billing_details_unknown")
                    or any(type(s[k]) is not int or s[k] < 0 for k in ("known_input_tokens", "known_output_tokens"))
                    or any(type(s[k]) is not bool for k in ("charged_complete", "list_cost_complete", "allowance_complete"))
                    or any(_amount(s[k]) is None for k in ("charged_usd_known", "list_cost_usd_known", "allowance_usd_known"))):
                raise ValueError
            if s["pending"] is not None:
                p = s["pending"]
                if (type(p) is not dict or set(p) != {"run_id", "round", "request_sha256", "status", "max_output_tokens"}
                        or not ID_RE.fullmatch(p["run_id"]) or type(p["round"]) is not int or not 1 <= p["round"] <= PROFILE["max_requests"]
                        or not re.fullmatch(r"[0-9a-f]{64}", p["request_sha256"]) or p["status"] not in {"pending", "unknown"}
                        or type(p["max_output_tokens"]) is not int or p["max_output_tokens"] != PROFILE["max_output_tokens"]
                        or s["usage_complete"] is not False): raise ValueError
            elif s["usage_complete"] is not True:
                raise ValueError
        except Exception:
            raise GoFailure("go_state_invalid") from None

    def _audit_set(self, entries: list[Path], state: dict, identities: dict) -> None:
        tokens_in = tokens_out = 0
        sums = {"charged_usd": Decimal(0), "list_cost_usd": Decimal(0), "allowance_usd": Decimal(0)}
        complete = {name: True for name in sums}
        expected_halt = None
        try:
            for path in entries:
                if path.is_symlink() or not path.is_file() or path.suffix != ".json" or not ID_RE.fullmatch(path.stem): raise ValueError
                run = _object(path)
                if (run.get("schema") != "chi-opencode-go-probe-run-v1" or run.get("run_id") != path.stem
                        or run.get("identity") != identities[path.stem] or run.get("status") not in {"complete", "failed"}
                        or type(run.get("requests")) is not list): raise ValueError
                for item in run["requests"]:
                    if (type(item) is not dict or item.get("status") != "settled"
                            or type(item.get("input_tokens")) is not int or item["input_tokens"] < 0
                            or type(item.get("output_tokens")) is not int or item["output_tokens"] < 0
                            or type(item.get("billing")) is not dict): raise ValueError
                    tokens_in += item["input_tokens"]; tokens_out += item["output_tokens"]
                    billing = item["billing"]
                    if set(billing) != {"charged_usd", "list_cost_usd", "allowance_usd", "billing_source"}:
                        raise ValueError
                    source, charged = billing["billing_source"], billing["charged_usd"]
                    inferred = ("billing_details_unknown" if source is None else
                                "billing_source_unexpected" if source not in {"go", "go-plus"}
                                or (charged is not None and Decimal(_amount(charged)) != 0) else
                                "billing_details_unknown" if any(billing[name] is None for name in sums) else None)
                    if item.get("billing_error") != inferred or (expected_halt is not None and inferred is not None):
                        raise ValueError
                    if inferred is not None: expected_halt = inferred
                    for name in sums:
                        amount = item["billing"].get(name)
                        if amount is None: complete[name] = False
                        else: sums[name] += Decimal(_amount(amount))
            if (tokens_in != state["known_input_tokens"] or tokens_out != state["known_output_tokens"]
                    or any(sums[name] != Decimal(state[name + "_known"]) for name in sums)
                    or expected_halt != state["halted"]
                    or any(complete[name] != state[key] for name, key in
                           (("charged_usd", "charged_complete"), ("list_cost_usd", "list_cost_complete"),
                            ("allowance_usd", "allowance_complete")))): raise ValueError
        except Exception:
            raise GoFailure("go_history_invalid") from None


    def _audit_runs(self) -> None:
        try:
            runs = self.root / "runs"
            if runs.is_symlink(): raise ValueError
            entries = list(runs.iterdir()) if runs.exists() else []
            by_id = {}
            for path in entries:
                if path.is_symlink() or not path.is_file() or path.suffix != ".json" or not ID_RE.fullmatch(path.stem): raise ValueError
                by_id[path.stem] = path
            transitions = self.state.get("source_transitions", [])
            if type(transitions) is not list: raise ValueError
            archives = self.root / "source-archives"
            if archives.is_symlink(): raise ValueError
            archive_names = {p.name for p in archives.iterdir()} if archives.exists() else set()
            if archive_names != {t["id"] + ".json" for t in transitions}: raise ValueError
            identities, previous_snapshot, previous_new = {}, {}, None
            for index, transition in enumerate(transitions):
                if (type(transition) is not dict or set(transition) != {"id", "reason", "old_identity", "new_identity", "accounting_sha256", "runs_sha256"}
                        or not re.fullmatch(r"[0-9a-f]{32}", transition["id"])
                        or type(transition["reason"]) is not str or not transition["reason"]
                        or type(transition["runs_sha256"]) is not dict
                        or (previous_new is not None and transition["old_identity"] != previous_new)):
                    raise ValueError
                archive = archives / (transition["id"] + ".json")
                raw = _read_regular(archive, 32 * 1024 * 1024)
                if _sha(raw) != transition["accounting_sha256"]: raise ValueError
                archived = _object(archive)
                if (archived.get("identity") != transition["old_identity"]
                        or archived.get("source_transitions", []) != transitions[:index]
                        or archived.get("pending") is not None or archived.get("usage_complete") is not True
                        or archived.get("halted") is not None): raise ValueError
                snapshot = transition["runs_sha256"]
                if not previous_snapshot.items() <= snapshot.items(): raise ValueError
                for run_id, digest in snapshot.items():
                    if run_id not in by_id or _sha(_read_regular(by_id[run_id], 32 * 1024 * 1024)) != digest: raise ValueError
                    if run_id not in identities: identities[run_id] = transition["old_identity"]
                self._audit_set([by_id[x] for x in snapshot], archived, identities)
                previous_snapshot, previous_new = snapshot, transition["new_identity"]
            if transitions and previous_new != self.state["identity"]: raise ValueError
            for run_id in by_id:
                if run_id not in identities: identities[run_id] = self.state["identity"]
            self._audit_set(entries, self.state, identities)
        except Exception:
            raise GoFailure("go_history_invalid") from None

    def reserve(self, round_number: int, raw: bytes, body: dict | None = None) -> None:
        if _object(self.state_path) != self.state or self.state["pending"] is not None or self.state["halted"] is not None:
            raise GoFailure("go_usage_unknown")
        entry = {"run_id": self.run_id, "round": round_number, "request_sha256": _sha(raw),
                 "status": "pending", "max_output_tokens": PROFILE["max_output_tokens"]}
        self.state["pending"], self.state["usage_complete"] = dict(entry), False
        if body is not None: entry["request_body"] = body
        self.run["requests"].append(entry)
        _atomic(self.state_path, self.state)
        _atomic(self.run_path, self.run)

    def unknown(self, code: str) -> None:
        if self.state["pending"] is not None:
            self.state["pending"]["status"] = "unknown"
            self.state["usage_complete"] = False
            self.run["requests"][-1]["status"] = "unknown"
            self.run["requests"][-1]["safe_error_code"] = code
            _atomic(self.state_path, self.state)
            _atomic(self.run_path, self.run)

    def settle(self, incoming: int, outgoing: int, billed: dict, halt: str | None) -> None:
        pending = self.state["pending"]
        if type(pending) is not dict or pending["run_id"] != self.run_id: raise GoFailure("go_pending_invalid")
        entry = self.run["requests"][-1]
        entry.update({"status": "settled", "input_tokens": incoming, "output_tokens": outgoing,
                      "usage_provenance": "provider_response", "billing": billed, "billing_error": halt})
        # Persist the full per-request evidence before releasing the shared pending claim.
        _atomic(self.run_path, self.run)
        self.state["known_input_tokens"] += incoming
        self.state["known_output_tokens"] += outgoing
        for field, complete in (("charged_usd", "charged_complete"), ("list_cost_usd", "list_cost_complete"),
                                ("allowance_usd", "allowance_complete")):
            if billed[field] is None:
                self.state[complete] = False
            else:
                key = field + "_known"
                self.state[key] = str(Decimal(self.state[key]) + Decimal(billed[field]))
        self.state["halted"] = halt
        self.state["pending"], self.state["usage_complete"] = None, True
        _atomic(self.state_path, self.state)

    def event(self, kind: str, **data) -> None:
        self.run["tool_events"].append({"kind": kind, **data})
        _atomic(self.run_path, self.run)

    def finish(self, status: str, code: str | None, elapsed: float) -> None:
        self.run.update(status=status, safe_error_code=code, elapsed_seconds=round(elapsed, 3))
        _atomic(self.run_path, self.run)

    def close(self):
        if getattr(self, "lock", None) is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN); os.close(self.lock); self.lock = None


class GoGuard(httpx.AsyncBaseTransport):
    """Exact-route, single-session transport for the fixed Go coding probe."""
    def __init__(self, journal: GoJournal, secret: str, session: str, lower: httpx.AsyncBaseTransport):
        if not isinstance(secret, str) or not secret.strip() or not re.fullmatch(r"chi-[0-9a-f]{32}", session):
            raise GoFailure("go_client_invalid")
        self.journal, self.secret, self.session, self.lower = journal, secret, session, lower
        self.rounds = 0
        self.error = None
        self.pending_calls: list[dict] = []
        self.seen_ids: set[str] = set()
        self.call_records: dict[str, dict] = {}
        self.inspection_call = None
        self.inspection_observed = False
        self.verified = False

    def _validate(self, request: httpx.Request, raw: bytes) -> dict:
        if self.error is not None: raise GoFailure(self.error)
        url = request.url
        if (request.method != "POST" or url.scheme != "https" or url.host != "opencode.ai" or url.port is not None
                or url.path != "/inference/go/openai/v1/chat/completions" or url.query or url.fragment or url.userinfo
                or len(raw) > 1_048_576): raise GoFailure("go_route_invalid")
        if (request.headers.get_list("user-agent") != [PROFILE["user_agent"]]
                or request.headers.get_list("x-opencode-session") != [self.session]
                or request.headers.get_list("authorization") != ["Bearer " + self.secret]):
            raise GoFailure("go_headers_invalid")
        try:
            body = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if (type(body) is not dict or body.get("model") != PROFILE["model"]
                    or set(body) != {"model", "messages", "tools", "max_tokens", "reasoning_effort", "thinking"}):
                raise ValueError
            if (type(body.get("max_tokens")) is not int or body["max_tokens"] != PROFILE["max_output_tokens"]
                    or body.get("reasoning_effort") != "high" or body.get("thinking") != {"type": "enabled"}
                    or body.get("stream", False) is not False):
                raise ValueError
            tools = body.get("tools")
            if type(tools) is not list or len(tools) != len(SCHEMAS): raise ValueError
            names = set()
            for tool in tools:
                fn = tool.get("function") if type(tool) is dict else None
                if (type(fn) is not dict or set(tool) != {"type", "function"} or tool.get("type") != "function"
                        or set(fn) != {"name", "description", "parameters", "strict"} or fn.get("name") not in SCHEMAS
                        or fn["name"] in names or fn.get("parameters") != SCHEMAS[fn["name"]]
                        or fn.get("description") != DESCRIPTIONS[fn["name"]] or fn.get("strict") is not False): raise ValueError
                names.add(fn["name"])
            messages = body.get("messages")
            if (type(messages) is not list or len(messages) < 2
                    or messages[0] != {"role": "system", "content": SYSTEM}
                    or messages[1] != {"role": "user", "content": INSTRUCTION}): raise ValueError
            pending, seen, seen_order = set(), set(), []
            observed_inspection = False
            for message in messages[2:]:
                if type(message) is not dict or message.get("role") not in {"assistant", "tool"}: raise ValueError
                if message["role"] == "assistant":
                    if pending: raise ValueError
                    if (set(message) != {"role", "content", "tool_calls", "reasoning_content"}
                            or type(message.get("reasoning_content")) is not str
                            or type(message.get("tool_calls")) is not list or len(message["tool_calls"]) != 1): raise ValueError
                    for call in message.get("tool_calls", []):
                        fn = call.get("function") if type(call) is dict else None
                        call_id = call.get("id") if type(call) is dict else None
                        if (type(call_id) is not str or not CALL_RE.fullmatch(call_id) or call_id in seen
                                or set(call) != {"id", "type", "function"} or call.get("type") != "function"
                                or type(fn) is not dict or set(fn) != {"name", "arguments"} or fn.get("name") not in SCHEMAS): raise ValueError
                        recorded = self.call_records.get(call_id)
                        if (recorded is None or recorded["name"] != fn["name"]
                                or json.loads(fn.get("arguments", ""), object_pairs_hook=_unique) != recorded["arguments"]
                                or message["reasoning_content"] != recorded["reasoning_content"]
                                or message["content"] != recorded["content"]):
                            raise ValueError
                        seen.add(call_id); seen_order.append(call_id); pending.add(call_id)
                else:
                    call_id = message.get("tool_call_id")
                    if set(message) != {"role", "tool_call_id", "content"} or call_id not in pending or type(message.get("content")) is not str: raise ValueError
                    if self.call_records[call_id].get("result") != message["content"]: raise ValueError
                    pending.remove(call_id)
                    if call_id == self.inspection_call and message["content"] == "def add(a, b):\n    return a - b\n":
                        observed_inspection = True
            if pending or seen_order != list(self.call_records): raise ValueError
            self.inspection_observed = observed_inspection
            if _contains_secret(body, self.secret, self.session): raise GoFailure("go_secret_in_body")
        except Exception:
            raise GoFailure("go_request_invalid") from None
        if self.rounds >= PROFILE["max_requests"]: raise GoFailure("go_request_limit_reached")
        return body

    def _response(self, payload: dict) -> None:
        from jsonschema import Draft202012Validator
        if payload.get("model") != PROFILE["model"]: raise GoFailure("go_response_model_mismatch")
        choices = payload.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise GoFailure("go_response_invalid")
        choice = choices[0]
        message = choice.get("message")
        if (type(message) is not dict or message.get("role") != "assistant"
                or message.get("function_call") is not None): raise GoFailure("go_response_invalid")
        if choice.get("finish_reason") == "stop":
            if (message.get("reasoning_content") is not None and type(message.get("reasoning_content")) is not str
                    or not self.verified or not isinstance(message.get("content"), str) or not message["content"].strip()
                    or message.get("tool_calls") not in (None, []) or self.pending_calls):
                raise GoFailure("go_final_invalid")
            return
        calls = message.get("tool_calls")
        if type(message.get("reasoning_content")) is not str: raise GoFailure("go_response_invalid")
        if choice.get("finish_reason") != "tool_calls" or type(calls) is not list or not calls:
            raise GoFailure("go_response_invalid")
        parsed, ids = [], set()
        for call in calls:
            try:
                if type(call) is not dict or call.get("type") != "function": raise ValueError
                call_id, fn = call["id"], call["function"]
                if (type(call_id) is not str or not CALL_RE.fullmatch(call_id) or call_id in ids or call_id in self.seen_ids
                        or type(fn) is not dict or fn.get("name") not in SCHEMAS): raise ValueError
                arguments = json.loads(fn["arguments"], object_pairs_hook=_unique,
                                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not Draft202012Validator(SCHEMAS[fn["name"]]).is_valid(arguments): raise ValueError
                if fn["name"] == "verify_patch" and not self.inspection_observed: raise ValueError
                ids.add(call_id); parsed.append({"id": call_id, "name": fn["name"], "arguments": arguments,
                                                 "reasoning_content": message["reasoning_content"], "content": message.get("content")})
            except Exception:
                raise GoFailure("go_tool_batch_invalid") from None
        if len(parsed) != 1: raise GoFailure("go_tool_batch_invalid")
        self.call_records.update({item["id"]: item for item in parsed})
        self.pending_calls.extend(parsed); self.seen_ids.update(ids)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            raw = request.content
            body = self._validate(request, raw)
            self.journal.reserve(self.rounds + 1, raw, body)
        except Exception as exc:
            self.error = exc.code if isinstance(exc, GoFailure) else "go_persistence_failed"
            raise GoFailure(self.error) from None
        self.rounds += 1
        start = time.monotonic()
        try:
            response = await self.lower.handle_async_request(request)
            if response.status_code != 200: raise GoFailure("go_http_error")
            raw_response = await response.aread()
            if len(raw_response) > 4 * 1024 * 1024: raise GoFailure("go_usage_unknown")
            entry = self.journal.run["requests"][-1]
            entry["response_sha256"] = _sha(raw_response)
            payload = json.loads(raw_response, object_pairs_hook=_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(payload) is not dict: raise GoFailure("go_usage_unknown")
            unsafe_body = _contains_secret(payload, self.secret, self.session)
            if not unsafe_body: entry["response_body"] = payload
            else: entry["response_redacted"] = "secret_detected"
            from b_provider_transport import GuardedTransport
            try: incoming, outgoing = GuardedTransport._usage(payload)
            except Exception: raise GoFailure("go_usage_unknown") from None
            over_limit = incoming > PROFILE["documented_context_tokens"] or outgoing > PROFILE["max_output_tokens"]
            billed, halt = _billing(payload["usage"])
            self.journal.run["requests"][-1]["elapsed_seconds"] = round(time.monotonic() - start, 3)
            self.journal.settle(incoming, outgoing, billed, halt)
            if halt is not None: raise GoFailure(halt)
            if unsafe_body: raise GoFailure("go_secret_in_body")
            if over_limit: raise GoFailure("go_usage_over_limit")
            self._response(payload)
            return response
        except BaseException as exc:
            code = exc.code if isinstance(exc, GoFailure) else "go_transport_unknown"
            self.error = code
            if self.journal.state["pending"] is not None:
                try: self.journal.unknown(code)
                except Exception: self.error = "go_persistence_failed"
            if isinstance(exc, asyncio.CancelledError): raise
            raise GoFailure(self.error) from None

    async def aclose(self) -> None:
        await self.lower.aclose()


def _matches_patch(code: str) -> bool:
    try:
        parsed = ast.parse(code)
        target = ast.parse("def add(a, b):\n    return a + b\n")
        return ast.dump(parsed, include_attributes=False) == ast.dump(target, include_attributes=False)
    except (SyntaxError, ValueError, TypeError):
        return False


def create_client(secret: str, journal: GoJournal, *, lower: httpx.AsyncBaseTransport | None = None):
    """Construct the pinned SDK client/model plus session-bound guard for this probe."""
    from openai import AsyncOpenAI
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    session = "chi-" + uuid.uuid4().hex
    guard = GoGuard(journal, secret, session, lower if lower is not None else httpx.AsyncHTTPTransport(retries=0, verify=True))
    journal.run["session_sha256"] = _sha(session.encode())
    journal.run["route"] = PROFILE["base_url"] + "/chat/completions"
    journal.run["model"] = PROFILE["model"]
    journal.run["user_agent"] = PROFILE["user_agent"]
    _atomic(journal.run_path, journal.run)
    client = AsyncOpenAI(api_key=secret, base_url=PROFILE["base_url"], max_retries=0,
                         default_headers={"User-Agent": PROFILE["user_agent"], "x-opencode-session": session},
                         http_client=httpx.AsyncClient(transport=guard, trust_env=False, follow_redirects=False,
                                                       timeout=httpx.Timeout(60.0, connect=10.0)))
    model = OpenAIChatCompletionsModel(model=PROFILE["model"], openai_client=client,
                                       should_replay_reasoning_content=_same_route_reasoning)
    return client, model, guard


def _same_route_reasoning(context: Any) -> bool:
    provider_data = getattr(getattr(context, "reasoning", None), "provider_data", {})
    return (getattr(context, "model", None) == PROFILE["model"]
            and (getattr(context, "base_url", "") or "").rstrip("/") == PROFILE["base_url"]
            and getattr(getattr(context, "reasoning", None), "origin_model", None) == PROFILE["model"]
            and type(provider_data) is dict and provider_data.get("origin_endpoint") == PROFILE["base_url"][:-3])


async def _run_probe(root: Path, run_id: str, secret: str, *, lower: httpx.AsyncBaseTransport | None = None) -> dict:
    from agents import Agent, Runner, ModelSettings, ModelRetrySettings, set_tracing_disabled
    from agents.tool import FunctionTool
    from agents.tracing import get_trace_provider
    from agents.models.openai_chatcompletions import Converter
    from model_runner_adapter import _patch_empty_history_compatibility
    identity = source_identity()
    journal = GoJournal(root, run_id, identity)
    start = time.monotonic()
    client = None
    saved = None
    status, code = "failed", None
    cancelled = None
    trace_disabled = get_trace_provider()._manual_disabled
    try:
        set_tracing_disabled(True)
        client, model, guard = create_client(secret, journal, lower=lower)
        saved = _patch_empty_history_compatibility(Converter, PROFILE["base_url"][:-3], PROFILE["model"])

        def tool(name, schema, callback):
            async def tracked(_ctx, payload):
                try: args = json.loads(payload, object_pairs_hook=_unique)
                except Exception: raise GoFailure("go_tool_arguments_invalid") from None
                selected = next((entry for entry in guard.pending_calls if entry["name"] == name and entry["arguments"] == args), None)
                if selected is None: raise GoFailure("go_tool_not_validated")
                if name == "inspect_code" and guard.inspection_call is not None: raise GoFailure("go_tool_order_invalid")
                if name == "verify_patch" and guard.verified: raise GoFailure("go_tool_order_invalid")
                guard.pending_calls.remove(selected)
                value = callback(args)
                guard.call_records[selected["id"]]["result"] = value
                if name == "inspect_code": guard.inspection_call = selected["id"]
                if name == "verify_patch": guard.verified = value == "verification:pass"
                journal.event("tool_returned", call_id=selected["id"], tool=name,
                              arguments_sha256=_sha(payload.encode()), result_sha256=_sha(value.encode()))
                if name == "verify_patch" and not guard.verified: raise GoFailure("go_verification_failed")
                return value
            return FunctionTool(name=name, description=DESCRIPTIONS[name], params_json_schema=schema,
                                on_invoke_tool=tracked, strict_json_schema=False)
        tools = [tool("inspect_code", INSPECT_SCHEMA, lambda _: "def add(a, b):\n    return a - b\n"),
                 tool("verify_patch", VERIFY_SCHEMA, lambda args: "verification:pass" if _matches_patch(args["code"]) else "verification:fail")]
        agent = Agent(name="synthetic-coding-probe", instructions=SYSTEM, model=model, tools=tools,
                      model_settings=ModelSettings(max_tokens=PROFILE["max_output_tokens"], reasoning={"effort": "high"},
                                                   extra_body={"thinking": {"type": "enabled"}},
                                                   extra_headers={"User-Agent": PROFILE["user_agent"]},
                                                   retry=ModelRetrySettings(max_retries=0)))
        result = await Runner.run(agent, input=INSTRUCTION, max_turns=PROFILE["max_requests"])
        if guard.error is not None or not guard.verified or not result.final_output:
            raise GoFailure(guard.error or "go_probe_incomplete")
        if _contains_secret(result.final_output, secret, guard.session): raise GoFailure("go_secret_in_body")
        journal.run["final_output"] = result.final_output
        status = "complete"
    except BaseException as exc:
        code = getattr(locals().get("guard"), "error", None) or (exc.code if isinstance(exc, GoFailure) else "go_probe_failed")
        if journal.state.get("pending") is not None:
            try: journal.unknown(code)
            except Exception: code = "go_persistence_failed"
        if isinstance(exc, asyncio.CancelledError): cancelled = exc
    finally:
        if saved is not None:
            Converter.message_to_output_items, Converter.items_to_messages = saved
        try:
            if client is not None: await client.close()
        except Exception:
            status, code = "failed", "go_cleanup_failed"
        try:
            journal.finish(status, code, time.monotonic() - start)
        finally:
            journal.close()
            set_tracing_disabled(trace_disabled)
    if cancelled is not None: raise cancelled
    return {"status": status, "safe_error_code": code, "run_id": run_id, "official_reward": None}


def plan() -> dict:
    _, profile_hash = load_profile()
    return {"mode": "fixed_synthetic_coding_probe", "route": PROFILE["base_url"] + "/chat/completions",
            "model": PROFILE["model"], "profile_sha256": profile_hash, "user_agent": PROFILE["user_agent"],
            "max_requests": PROFILE["max_requests"], "max_output_tokens": PROFILE["max_output_tokens"],
            "documented_context_tokens": PROFILE["documented_context_tokens"],
            "context_evidence": PROFILE["context_evidence"], "currency": "USD", "automatic_retries": 0,
            "credentials_read": False, "world_created": False, "official_reward": None}


def preflight() -> dict:
    result = plan()
    identity = source_identity()
    if DEFAULT_ROOT.exists():
        try:
            from b_provider_transport import _reject_symlink_ancestors
            _reject_symlink_ancestors(DEFAULT_ROOT, "path_invalid")
            if (DEFAULT_ROOT / ".rebind-pending").exists() or (DEFAULT_ROOT / ".rebind-pending").is_symlink(): raise ValueError
            if not (DEFAULT_ROOT / "accounting.json").exists():
                entries = list(DEFAULT_ROOT.iterdir())
                if entries and not (len(entries) == 1 and entries[0].name == ".lock" and entries[0].is_file() and not entries[0].is_symlink()): raise ValueError
                result["ledger_status"] = "not_initialized"
                result["identity"] = identity
                result["account_prior_history"] = "unknown"
                return result
            state = _object(DEFAULT_ROOT / "accounting.json")
            if state.get("identity") != identity or state.get("pending") is not None or state.get("usage_complete") is not True or state.get("halted") is not None:
                raise ValueError
            result["ledger_status"] = "existing_unlocked_unverified_history"
        except Exception:
            raise GoFailure("go_preflight_unavailable") from None
    else:
        result["ledger_status"] = "not_initialized"
    result["identity"] = identity
    result["account_prior_history"] = "unknown"
    return result


def rebind_source(root: Path, reason: str) -> dict:
    if type(reason) is not str or not reason.strip() or len(reason) > 200 or any(ord(c) < 32 for c in reason):
        raise GoFailure("go_rebind_reason_invalid")
    if not root.is_dir() or root.is_symlink(): raise GoFailure("go_history_missing")
    old_identity = _object(root / "accounting.json").get("identity")
    new_identity = source_identity()
    journal = GoJournal(root, "rebind-source", old_identity, maintenance=True)
    try:
        old = journal.state
        if (type(old_identity) is not dict or old_identity == new_identity
                or old_identity.get("profile_sha256") != new_identity.get("profile_sha256")
                or old_identity.get("sdk") != new_identity.get("sdk")
                or not all(old[k] is True for k in ("charged_complete", "list_cost_complete", "allowance_complete"))):
            raise GoFailure("go_rebind_not_allowed")
        original = _read_regular(journal.state_path, 32 * 1024 * 1024)
        if _object(journal.state_path) != old: raise GoFailure("go_state_invalid")
        runs = root / "runs"
        snapshot = {p.stem: _sha(_read_regular(p, 32 * 1024 * 1024)) for p in runs.iterdir()} if runs.exists() else {}
        transition_id = uuid.uuid4().hex
        marker = root / ".rebind-pending"
        _atomic(marker, {"schema": "chi-go-rebind-pending-v1", "id": transition_id}, exclusive=True)
        archives = root / "source-archives"
        archives.mkdir(exist_ok=True)
        if archives.is_symlink() or not archives.is_dir(): raise GoFailure("go_history_invalid")
        archive = archives / (transition_id + ".json")
        fd = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(original); stream.flush(); os.fsync(stream.fileno())
        directory = os.open(archives, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        transition = {"id": transition_id, "reason": reason.strip(), "old_identity": old_identity,
                      "new_identity": new_identity, "accounting_sha256": _sha(original), "runs_sha256": snapshot}
        updated = dict(old)
        updated["identity"] = new_identity
        updated["source_transitions"] = old.get("source_transitions", []) + [transition]
        _atomic(journal.state_path, updated)
        marker.unlink()
        directory = os.open(root, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        return {"status": "rebound", "transition_id": transition_id, "accounting_sha256": transition["accounting_sha256"],
                "historical_runs": len(snapshot)}
    finally:
        journal.close()


def _offline_responder():
    responses = [
        {"role": "assistant", "content": None, "reasoning_content": "synthetic", "tool_calls": [
            {"id": "inspect-1", "type": "function", "function": {"name": "inspect_code", "arguments": "{}"}}]},
        {"role": "assistant", "content": None, "reasoning_content": "synthetic", "tool_calls": [
            {"id": "verify-1", "type": "function", "function": {"name": "verify_patch", "arguments": json.dumps({"code": "def add(a, b):\n    return a + b\n"})}}]},
        {"role": "assistant", "content": "The corrected function passed verification.", "reasoning_content": "synthetic"},
    ]
    def reply(request):
        if not responses: raise AssertionError("unexpected request")
        message = responses.pop(0)
        return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion", "created": 1,
            "model": PROFILE["model"], "choices": [{"index": 0, "message": message,
            "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "cost": 0,
                      "opencode": {"billing_source": "go", "list_cost": 0.0001, "allowance": 0.0001}}})
    return reply


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("plan", "preflight", "offline"): sub.add_parser(name)
    rebind = sub.add_parser("rebind-source")
    rebind.add_argument("--reason", required=True)
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    # Never print provider bodies, tool arguments, or exception text.
    logging.disable(logging.CRITICAL)
    try:
        if args.mode == "plan": result = plan()
        elif args.mode == "preflight": result = preflight()
        elif args.mode == "rebind-source": result = rebind_source(DEFAULT_ROOT, args.reason)
        elif args.mode == "offline":
            with tempfile.TemporaryDirectory(prefix="opencode-go-offline-") as directory:
                result = asyncio.run(_run_probe(Path(directory), "offline-synthetic", "synthetic-key",
                                                lower=httpx.MockTransport(_offline_responder())))
        else:
            if not ID_RE.fullmatch(args.run_id): raise GoFailure("run_id_invalid")
            secret = os.environ.get(PROFILE["key_env"])
            if type(secret) is not str or not secret.strip() or "\n" in secret or "\r" in secret:
                raise GoFailure("go_credential_missing")
            result = asyncio.run(_run_probe(DEFAULT_ROOT, args.run_id, secret))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") != "failed" else 1
    except Exception as exc:
        code = exc.code if isinstance(exc, GoFailure) else "go_probe_unavailable"
        print(json.dumps({"status": "failed", "safe_error_code": code, "official_reward": None}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
