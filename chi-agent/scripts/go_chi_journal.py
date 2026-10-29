"""Persistent USD journal primitive for Go CHI; not a live execution entry.

An integration must hold an independently audited local Go development journal
lock for the entire session when operating in that development environment.
This module does not itself establish that external prerequisite.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from decimal import Decimal
from pathlib import Path

from opencode_go_provider import GoFailure, _atomic, _billing, _object
from b_provider_transport import _reject_symlink_ancestors

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _run_digest(run: dict) -> str:
    return hashlib.sha256(json.dumps(run, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _receipt(run: dict, identity: str) -> dict:
    return {"schema": "chi-go-b-success-v1", "identity": identity, "run": run["run"],
            "evaluation": run["evaluation"], "task": run["task"], "attempt": run["attempt"],
            "run_sha256": _run_digest(run)}


def publish_b_receipt(root: Path, identity: str, run: dict) -> None:
    """Publish only after the SDK client and both journal locks have closed."""
    if run.get("kind") != "coding_b" or run.get("status") != "complete":
        raise GoFailure("chi_b_receipt_invalid")
    directory = Path(root) / "b-receipts"
    _reject_symlink_ancestors(directory, "chi_path_invalid")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink_ancestors(directory, "chi_path_invalid")
    _atomic(directory / (run["run"] + ".json"), _receipt(run, identity), exclusive=True)


class ChiJournal:
    """Exclusive one-identity namespace with immutable attempt claims.

    Each request is reserved durably before dispatch. Missing or unknown usage
    blocks every later attempt in the namespace. Source changes require a new,
    separately reviewed migration; this class never silently rebinds identity.
    """
    def __init__(self, root: Path, *, identity: str, evaluation: str, task: str,
                 attempt: str, run: str, kind: str = "chi", require_b: bool = False,
                 launch: dict | None = None):
        if (type(identity) is not str or not DIGEST.fullmatch(identity)
                or kind not in {"chi", "coding_b"}
                or (launch is not None and type(launch) is not dict)
                or any(type(x) is not str or not ID.fullmatch(x)
                       for x in (evaluation, task, attempt, run))):
            raise GoFailure("chi_identity_invalid")
        self.root = Path(root)
        self.lock = None
        try:
            _reject_symlink_ancestors(self.root, "chi_path_invalid")
            self.root.mkdir(parents=True, exist_ok=True)
            _reject_symlink_ancestors(self.root, "chi_path_invalid")
            self.lock = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path = self.root / "chi-accounting.json"
            if not self.path.exists():
                if any(p.name != ".lock" for p in self.root.iterdir()):
                    raise GoFailure("chi_history_missing")
                _atomic(self.path, {"schema": "chi-go-evaluation-usd-v1", "identity": identity,
                                    "account_prior_history": "unknown", "attempts": [], "pending": None,
                                    "halted": None}, exclusive=True)
            self.state = _object(self.path)
            self._validate(identity)
            if self.state["pending"] is not None:
                raise GoFailure("chi_usage_unknown")
            if self.state["halted"] is not None:
                raise GoFailure("chi_billing_halted")
            if require_b:
                def valid_b(item):
                    if not (item["kind"] == "coding_b" and item["status"] == "complete"
                            and item["task"] == "synthetic-coding-b"
                            and item["launch"].get("kind") == "coding_b"
                            and len(item["requests"]) >= 3
                            and [event.get("tool") for event in item["tool_events"]] == ["inspect_code", "verify_patch"]
                            and item["tool_events"][0].get("result_sha256") == hashlib.sha256(b"def add(a, b):\n    return a - b\n").hexdigest()
                            and item["tool_events"][1].get("result_sha256") == hashlib.sha256(b"verification:pass").hexdigest()):
                        return False
                    path = self.root / "b-receipts" / (item["run"] + ".json")
                    try:
                        _reject_symlink_ancestors(path.parent, "chi_path_invalid")
                        return _object(path) == _receipt(item, identity)
                    except Exception:
                        return False
                if kind != "chi" or not any(valid_b(item) for item in self.state["attempts"]):
                    raise GoFailure("chi_b_receipt_missing")
            if any(a["run"] == run or (a["evaluation"], a["task"], a["attempt"]) == (evaluation, task, attempt)
                   for a in self.state["attempts"]):
                raise GoFailure("chi_attempt_or_run_exists")
            self.run = {"evaluation": evaluation, "task": task, "attempt": attempt, "run": run,
                        "kind": kind, "status": "started", "requests": [], "patient_binding_events": [],
                        "claim_done": False, "tool_events": [], "safe_error_code": None,
                        "launch": launch or {}}
            self.run_doc = self.run
            self.state["attempts"].append(self.run)
            self._persist()
        except BaseException:
            self.close()
            raise

    def _validate(self, identity: str) -> None:
        try:
            s = self.state
            if (type(s) is not dict or set(s) != {"schema", "identity", "account_prior_history", "attempts", "pending", "halted"}
                    or s["schema"] != "chi-go-evaluation-usd-v1" or s["identity"] != identity
                    or s["account_prior_history"] != "unknown" or type(s["attempts"]) is not list
                    or s["halted"] not in (None, "billing_details_unknown", "billing_source_unexpected")):
                raise ValueError
            identities, runs, halt = set(), set(), None
            pending = None
            for a in s["attempts"]:
                if (type(a) is not dict or set(a) != {"evaluation", "task", "attempt", "run", "kind", "status", "requests", "patient_binding_events", "claim_done", "tool_events", "safe_error_code", "launch"}
                        or any(type(a[k]) is not str or not ID.fullmatch(a[k]) for k in ("evaluation", "task", "attempt", "run"))
                        or a["kind"] not in {"chi", "coding_b"}
                        or type(a["patient_binding_events"]) is not list
                        or type(a["claim_done"]) is not bool
                        or type(a["launch"]) is not dict
                        or type(a["tool_events"]) is not list
                        or any(type(event) is not dict for event in a["tool_events"])
                        or (a["safe_error_code"] is not None and (type(a["safe_error_code"]) is not str
                            or not re.fullmatch(r"[a-z0-9_]{1,64}", a["safe_error_code"])))
                        or any(type(event) is not dict or type(event.get("event")) is not str for event in a["patient_binding_events"])
                        or a["status"] not in {"started", "complete", "failed"} or type(a["requests"]) is not list
                        or len(a["requests"]) > (6 if a["kind"] == "coding_b" else 50)):
                    raise ValueError
                key = (a["evaluation"], a["task"], a["attempt"])
                if key in identities or a["run"] in runs:
                    raise ValueError
                identities.add(key); runs.add(a["run"])
                confirms = 0
                for index, item in enumerate(a["requests"], 1):
                    if (type(item) is not dict or item.get("round") != index
                            or item.get("purpose") not in {"main", "confirmation"}
                            or (a["kind"] == "coding_b" and item.get("purpose") != "main")
                            or item.get("max_tokens") != (1024 if a["kind"] == "coding_b" else 8192 if item.get("purpose") == "main" else 32768)
                            or type(item.get("request_sha256")) is not str or not DIGEST.fullmatch(item["request_sha256"])):
                        raise ValueError
                    confirms += item["purpose"] == "confirmation"
                    if confirms > 2 or halt is not None or pending is not None:
                        raise ValueError
                    if item.get("status") in {"pending", "unknown"}:
                        if set(item) != {"round", "purpose", "max_tokens", "request_sha256", "status"}:
                            raise ValueError
                        pending = {"run": a["run"], "round": index}
                    elif item.get("status") == "settled":
                        if (set(item) != {"round", "purpose", "max_tokens", "request_sha256", "status", "usage", "billing", "billing_error"}
                                or type(item["usage"]) is not dict or set(item["usage"]) != {"input_tokens", "output_tokens"}
                                or any(type(v) is not int or v < 0 for v in item["usage"].values())
                                or type(item["billing"]) is not dict):
                            raise ValueError
                        billed = item["billing"]
                        if set(billed) != {"charged_usd", "list_cost_usd", "allowance_usd", "billing_source"}:
                            raise ValueError
                        for name in ("charged_usd", "list_cost_usd", "allowance_usd"):
                            if billed[name] is not None and (type(billed[name]) is not str or not Decimal(billed[name]).is_finite() or Decimal(billed[name]) < 0):
                                raise ValueError
                        inferred = ("billing_details_unknown" if billed["billing_source"] is None else
                                    "billing_source_unexpected" if billed["billing_source"] not in {"go", "go-plus"}
                                    or (billed["charged_usd"] is not None and Decimal(billed["charged_usd"]) != 0) else
                                    "billing_details_unknown" if any(billed[k] is None for k in ("charged_usd", "list_cost_usd", "allowance_usd")) else None)
                        if inferred != item["billing_error"]:
                            raise ValueError
                        halt = inferred
                    else:
                        raise ValueError
            if pending != s["pending"] or halt != s["halted"]:
                raise ValueError
        except Exception:
            raise GoFailure("chi_history_invalid") from None

    def _persist(self):
        _atomic(self.path, self.state)

    def record_claim(self) -> None:
        self.run["claim_done"] = True
        self._persist()

    def record_tool(self, call_id: str, name: str, result: str) -> None:
        self.run["tool_events"].append({"call_id": call_id, "tool": name,
                                        "result_sha256": hashlib.sha256(result.encode()).hexdigest()})
        self._persist()

    def reserve(self, raw: bytes, purpose: str) -> None:
        if self.state["pending"] is not None or self.state["halted"] is not None:
            raise GoFailure("chi_usage_unknown")
        if purpose not in {"main", "confirmation"} or type(raw) is not bytes:
            raise GoFailure("chi_reservation_invalid")
        if self.run["kind"] == "coding_b" and purpose != "main":
            raise GoFailure("chi_reservation_invalid")
        if len(self.run["requests"]) >= (6 if self.run["kind"] == "coding_b" else 50):
            raise GoFailure("chi_request_limit")
        if purpose == "confirmation" and sum(x["purpose"] == "confirmation" for x in self.run["requests"]) >= 2:
            raise GoFailure("chi_confirmation_limit")
        entry = {"round": len(self.run["requests"]) + 1, "purpose": purpose,
                 "max_tokens": 1024 if self.run["kind"] == "coding_b" else 8192 if purpose == "main" else 32768,
                 "request_sha256": hashlib.sha256(raw).hexdigest(), "status": "pending"}
        self.run["requests"].append(entry)
        self.state["pending"] = {"run": self.run["run"], "round": entry["round"]}
        self._persist()

    def settle(self, usage: dict) -> None:
        if self.state["pending"] is None:
            raise GoFailure("chi_pending_invalid")
        try:
            incoming, outgoing = usage["prompt_tokens"], usage["completion_tokens"]
            if any(type(x) is not int or x < 0 for x in (incoming, outgoing)):
                raise ValueError
            billed, halt = _billing(usage)
        except Exception:
            raise GoFailure("chi_usage_unknown") from None
        entry = self.run["requests"][-1]
        entry.update(status="settled", usage={"input_tokens": incoming, "output_tokens": outgoing},
                     billing=billed, billing_error=halt)
        self.state["halted"] = halt
        self.state["pending"] = None
        self._persist()
        if halt:
            raise GoFailure(halt)

    def finish(self, status: str, error: str | None = None) -> None:
        if status not in {"complete", "failed"} or self.run["status"] != "started":
            raise GoFailure("chi_status_invalid")
        if error is not None and (type(error) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", error)):
            raise GoFailure("chi_status_invalid")
        self.run["status"] = status
        self.run["safe_error_code"] = error
        self._persist()

    def usage_totals(self) -> dict:
        """Report three distinct USD measures; never combine allowance and cost."""
        names = ("charged_usd", "list_cost_usd", "allowance_usd")
        totals = {name: Decimal(0) for name in names}
        complete = {name: True for name in names}
        incoming = outgoing = 0
        for attempt in self.state["attempts"]:
            for request in attempt["requests"]:
                if request["status"] != "settled":
                    for name in names:
                        complete[name] = False
                    continue
                incoming += request["usage"]["input_tokens"]
                outgoing += request["usage"]["output_tokens"]
                for name in names:
                    value = request["billing"][name]
                    if value is None:
                        complete[name] = False
                    else:
                        totals[name] += Decimal(value)
        return {"input_tokens_known": incoming, "output_tokens_known": outgoing,
                "usd": {name: {"known": str(totals[name]), "complete": complete[name]} for name in names},
                "account_prior_history": "unknown"}

    def close(self) -> None:
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            os.close(self.lock)
            self.lock = None
