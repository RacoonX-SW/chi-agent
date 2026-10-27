"""Validated accounting and monetary-stop policies, separate from model profiles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCAL_POLICY_PATH = ROOT / "profiles" / "local-development-policy.json"
POLICY_SCHEMA = "chi-execution-accounting-policy-v1"
_MONEY_RE = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")


class PolicyFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExecutionPolicy:
    raw: dict[str, Any]
    sha256: str
    policy_id: str
    scope: str
    mode: str
    hard_cap_cny: Decimal | None


_LOCAL_EXPECTED = {
    "schema": POLICY_SCHEMA,
    "policy_id": "local-development-shared-b-c-5-cny-v1",
    "scope": "local_development",
    "mode": "capped",
    "hard_cap_cny": "5",
    "budget_group": "shared_B_C",
    "cost_basis": "provider_profile_peak_upper_estimate_not_billed",
}
_EVALUATION_COMMON = {
    "schema": POLICY_SCHEMA,
    "policy_id": "identified-evaluation-policy-rehearsal-v1",
    "scope": "evaluation_rehearsal",
    "budget_group": "per_attempt",
    "cost_basis": "provider_profile_peak_upper_estimate_not_organizer_billing",
}

_REAL_DEVELOPMENT_EXPECTED = {
    "schema": POLICY_SCHEMA,
    "policy_id": "real-development-repeated-b-c-record-only-v1",
    "scope": "real_development",
    "mode": "record_only",
    "hard_cap_cny": None,
    "budget_group": "shared_B_C",
    "cost_basis": "provider_profile_peak_upper_estimate_not_billed",
}


def _strict_money(value: Any) -> Decimal:
    if type(value) is not str or _MONEY_RE.fullmatch(value) is None:
        raise PolicyFailure("execution_policy_invalid")
    amount = Decimal(value)
    if not amount.is_finite() or amount <= 0:
        raise PolicyFailure("execution_policy_invalid")
    return amount


def _hash(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _build(raw: Any) -> ExecutionPolicy:
    if type(raw) is not dict:
        raise PolicyFailure("execution_policy_invalid")
    if raw == _LOCAL_EXPECTED and all(type(raw[k]) is type(v) for k, v in _LOCAL_EXPECTED.items()):
        cap = _strict_money(raw["hard_cap_cny"])
        return ExecutionPolicy(raw=dict(raw), sha256=_hash(raw), policy_id=raw["policy_id"],
                               scope=raw["scope"], mode=raw["mode"], hard_cap_cny=cap)
    if raw == _REAL_DEVELOPMENT_EXPECTED and all(type(raw[k]) is type(v) for k, v in _REAL_DEVELOPMENT_EXPECTED.items()):
        return ExecutionPolicy(raw=dict(raw), sha256=_hash(raw), policy_id=raw["policy_id"],
                               scope=raw["scope"], mode=raw["mode"], hard_cap_cny=None)
    expected_keys = set(_EVALUATION_COMMON) | {"mode", "hard_cap_cny"}
    if set(raw) != expected_keys or any(type(raw.get(k)) is not type(v) for k, v in _EVALUATION_COMMON.items()):
        raise PolicyFailure("execution_policy_invalid")
    if any(raw.get(k) != v for k, v in _EVALUATION_COMMON.items()):
        raise PolicyFailure("execution_policy_invalid")
    mode = raw.get("mode")
    cap_value = raw.get("hard_cap_cny")
    if mode == "record_only" and cap_value is None:
        cap = None
    elif mode == "capped":
        cap = _strict_money(cap_value)
    else:
        raise PolicyFailure("execution_policy_invalid")
    return ExecutionPolicy(raw=dict(raw), sha256=_hash(raw), policy_id=raw["policy_id"],
                           scope=raw["scope"], mode=mode, hard_cap_cny=cap)


def load_local_policy(path: Path = LOCAL_POLICY_PATH) -> ExecutionPolicy:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
            raise ValueError
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                         parse_constant=lambda _s: (_ for _ in ()).throw(ValueError()))
    except Exception:
        raise PolicyFailure("execution_policy_unreadable") from None
    try:
        policy = _build(raw)
    except PolicyFailure:
        raise
    if policy.scope != "local_development" or policy.raw != _LOCAL_EXPECTED:
        raise PolicyFailure("execution_policy_untrusted")
    return policy


def load_real_development_policy() -> ExecutionPolicy:
    """Return the fixed, distinct policy for explicitly continued real development."""
    return _build(_REAL_DEVELOPMENT_EXPECTED)


def make_evaluation_policy(mode: str, cap_cny: str | Decimal | None = None) -> ExecutionPolicy:
    if type(mode) is not str or mode not in {"record_only", "capped"}:
        raise PolicyFailure("execution_policy_invalid")
    if mode == "record_only":
        if cap_cny is not None:
            raise PolicyFailure("execution_policy_invalid")
        raw_cap = None
    else:
        raw_cap = str(cap_cny) if type(cap_cny) is Decimal else cap_cny
        _strict_money(raw_cap)
    return _build({**_EVALUATION_COMMON, "mode": mode, "hard_cap_cny": raw_cap})


def is_validated_policy(policy: Any) -> bool:
    if type(policy) is not ExecutionPolicy:
        return False
    try:
        current = _build(policy.raw)
    except PolicyFailure:
        return False
    return (
        type(policy.sha256) is str and policy.sha256 == current.sha256
        and type(policy.policy_id) is str and policy.policy_id == current.policy_id
        and type(policy.scope) is str and policy.scope == current.scope
        and type(policy.mode) is str and policy.mode == current.mode
        and ((policy.hard_cap_cny is None and current.hard_cap_cny is None)
             or (type(policy.hard_cap_cny) is Decimal and policy.hard_cap_cny == current.hard_cap_cny))
    )
