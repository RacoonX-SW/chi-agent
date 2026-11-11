"""Read-only summary for one caller-supplied Go CHI ledger root.

Package-external on purpose: it is not part of ``PACKAGE_FILES`` and never
reserves, settles, acknowledges, rebinds or writes anything. Validation is done
by the existing strict readers; this module only projects allowlisted fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

from chi_agent.evaluation_bundle import _read_regular_bounded
from chi_agent.journal import MAX_STATE_BYTES, inspect_history
from chi_agent.opencode_go_provider import GoFailure, _unique

SCHEMA = "chi-go-run-summary-v1"
CURRENCY = "USD"
BILLING_FIELDS = ("charged_usd", "list_cost_usd", "allowance_usd")


class SummaryError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _usd(value):
    if value is None:
        return None
    try:
        return str(Decimal(value))
    except Exception:
        raise SummaryError("summary_billing_invalid") from None


def _billing_view(billing: dict | None) -> dict:
    billing = billing if type(billing) is dict else {}
    view = {"currency": CURRENCY}
    for field in BILLING_FIELDS:
        view[field] = _usd(billing.get(field))
    view["billing_source"] = billing.get("billing_source")
    return view


def _request_view(request: dict) -> dict:
    usage = request.get("usage")
    tokens = None
    if type(usage) is dict:
        tokens = {"input_tokens": usage.get("input_tokens"),
                  "output_tokens": usage.get("output_tokens")}
    return {
        "round": request.get("round"),
        "purpose": request.get("purpose"),
        "max_tokens": request.get("max_tokens"),
        "status": request.get("status"),
        "tokens": tokens,
        "billing": _billing_view(request.get("billing")),
        "billing_error": request.get("billing_error"),
    }


def _aggregate(requests: list[dict]) -> dict:
    purposes: dict[str, dict] = {}
    totals = {"requests": 0, "settled": 0, "input_tokens_known": 0, "output_tokens_known": 0,
              "unknown_tokens": 0, "currency": CURRENCY,
              "usd": {field: {"known": "0", "complete": True} for field in BILLING_FIELDS}}
    for request in requests:
        purpose = request.get("purpose")
        bucket = purposes.setdefault(purpose, {
            "requests": 0, "settled": 0, "input_tokens_known": 0, "output_tokens_known": 0,
            "unknown_tokens": 0, "currency": CURRENCY,
            "usd": {field: {"known": "0", "complete": True} for field in BILLING_FIELDS}})
        for target in (totals, bucket):
            target["requests"] += 1
        if request.get("status") == "settled":
            for target in (totals, bucket):
                target["settled"] += 1
            usage = request.get("usage") or {}
            for target in (totals, bucket):
                target["input_tokens_known"] += usage.get("input_tokens", 0)
                target["output_tokens_known"] += usage.get("output_tokens", 0)
            billing = request.get("billing") or {}
            for target in (totals, bucket):
                for field in BILLING_FIELDS:
                    value = billing.get(field)
                    if value is None:
                        target["usd"][field]["complete"] = False
                    else:
                        target["usd"][field]["known"] = str(
                            Decimal(target["usd"][field]["known"]) + Decimal(value))
        else:
            for target in (totals, bucket):
                target["unknown_tokens"] += 1
                for field in BILLING_FIELDS:
                    target["usd"][field]["complete"] = False
    return {"totals": totals, "by_purpose": purposes}


def _run_view(attempt: dict) -> dict:
    requests = [_request_view(item) for item in attempt.get("requests", [])]
    launch = attempt.get("launch") if type(attempt.get("launch")) is dict else {}
    view = {
        "run": attempt.get("run"),
        "task": attempt.get("task"),
        "kind": attempt.get("kind"),
        "role": launch.get("role"),
        "status": attempt.get("status"),
        "safe_error_code": attempt.get("safe_error_code"),
        "fee_policy": launch.get("fee_policy"),
        "requests": requests,
    }
    view.update(_aggregate(attempt.get("requests", [])))
    return view


def _project(inspection: dict, state: dict, selected: str | None) -> dict:
    attempts = state.get("attempts", [])
    if selected is not None:
        runs = [attempt for attempt in attempts if attempt.get("run") == selected]
        if not runs:
            raise SummaryError("summary_run_missing")
        mode = "run"
    else:
        runs = list(attempts)
        mode = "all"
    views = [_run_view(attempt) for attempt in runs]
    totals = _aggregate([request for attempt in runs for request in attempt.get("requests", [])])
    return {
        "schema": SCHEMA,
        "execution_allowed": False,
        "selection": {"mode": mode, "run": selected},
        "identity": inspection["identity"],
        "accounting_sha256": inspection["accounting_sha256"],
        "validation": {
            "status": inspection["status"],
            "pending": inspection.get("pending"),
            "halted": inspection.get("halted"),
            "missing": inspection.get("missing", []),
            "pending_request": inspection.get("pending_request"),
            "acknowledged_unsettled": inspection.get("acknowledged_unsettled", []),
            "reconciled_provider_timeouts": inspection.get("reconciled_provider_timeouts", []),
            "input_summaries": inspection.get("input_summaries", []),
        },
        "runs": views,
        "totals": totals["totals"],
        "by_purpose": totals["by_purpose"],
        "notes": [
            "Known tokens exclude unsettled/unknown requests; they are not zero.",
            "Missing fee fields stay null with complete=false.",
            "execution_allowed is always false; this tool never grants admission.",
        ],
    }


def summarize(root: Path, identity: str, accounting_sha256: str,
              selected: str | None = None) -> dict:
    root = Path(root)
    if not root.is_dir():
        raise SummaryError("summary_root_invalid")
    inspection = inspect_history(root, identity, accounting_sha256)
    # Re-read once and require the same hash the inspection just validated. A
    # concurrent writer either leaves identical bytes (hash matches) or the
    # snapshot changed and the caller gets an explicit error instead of an old
    # hash paired with new content.
    raw = _read_regular_bounded(root / "chi-accounting.json", MAX_STATE_BYTES, "chi_history_invalid")
    if hashlib.sha256(raw).hexdigest() != accounting_sha256:
        raise SummaryError("summary_snapshot_changed")
    try:
        state = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise SummaryError("summary_snapshot_changed") from None
    if type(state) is not dict:
        raise SummaryError("summary_snapshot_changed")
    return _project(inspection, state, selected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Go CHI run summary (package-external)")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--accounting-sha256", required=True)
    parser.add_argument("--run", help="explicit run id; omit to summarize every run")
    args = parser.parse_args(argv)
    try:
        result = summarize(args.root, args.identity, args.accounting_sha256, args.run)
    except SummaryError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "code": exc.code}, sort_keys=True),
              file=sys.stderr)
        return 1
    except GoFailure as exc:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "code": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({"schema": SCHEMA, "status": "failed", "code": "summary_lock_unavailable"},
                         sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
