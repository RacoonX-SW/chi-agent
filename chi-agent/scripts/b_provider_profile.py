"""Strict public-facts profile and read-only preflight for prepared stage B."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "deepseek-flash-prepared.json"
PRICE_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
MODEL_SOURCE = "https://api-docs.deepseek.com/zh-cn/api/list-models/"
PROFILE_FRESHNESS_DAYS = 30

EXPECTED: dict[str, Any] = {
    "schema": "chi-prepared-provider-profile-v1",
    "profile_id": "deepseek-flash-prepared-2026-10-26-v1",
    "candidate": "deepseek-flash",
    "model": "deepseek-flash",
    "documented_model_mapping": "DeepSeek-V4.1-Flash-1017",
    "model_mapping_status": "documentation_only_not_provider_verified",
    "response_model": "deepseek-flash",
    "response_model_policy": "exact_candidate_match",
    "endpoint": "https://api.deepseek.com",
    "api": "chat_completions",
    "key_env": "DEEPSEEK_API_KEY",
    "thinking": {"type": "enabled"},
    "reasoning_effort": "high",
    "max_rounds": 30,
    "max_output_tokens": 8192,
    "documented_output_ceiling": {
        "tokens": 393216,
        "source": MODEL_SOURCE,
        "checked_on": "2026-10-26",
    },
    "input_reservation": {
        "tokens": 1048576,
        "kind": "documented_context_ceiling",
        "measurement": "documented_not_measured",
        "source": MODEL_SOURCE,
        "checked_on": "2026-10-26",
    },
    "pricing": {
        "currency": "CNY",
        "input_peak_cache_miss_per_million": 2,
        "output_peak_per_million": 8,
        "version": "DeepSeek-V4.1-Flash-1017",
        "source": PRICE_SOURCE,
        "checked_on": "2026-10-26",
        "estimate_kind": "conservative_peak_upper_estimate_not_billed_cost",
    },
    "execution": {"real_api_enabled": False, "actual_calls_authorized": False, "authentication": "unverified"},
}


class ProfileFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _same_typed_value(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_typed_value(actual[k], expected[k]) for k in expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_typed_value(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


@dataclass(frozen=True)
class ProviderProfile:
    raw: dict[str, Any]
    sha256: str
    input_price: Decimal
    output_price: Decimal
    input_reserve_tokens: int
    max_output_tokens: int
    max_rounds: int

    @property
    def model(self) -> str:
        return self.raw["model"]

    @property
    def endpoint(self) -> str:
        return self.raw["endpoint"]


def load_profile(path: Path = PROFILE_PATH, *, today: dt.date | None = None) -> ProviderProfile:
    try:
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes, object_pairs_hook=_object_without_duplicates,
                          parse_constant=lambda _s: (_ for _ in ()).throw(ValueError("constant")))
    except Exception:
        raise ProfileFailure("profile_unreadable") from None
    if not isinstance(data, dict) or not _same_typed_value(data, EXPECTED):
        raise ProfileFailure("profile_untrusted_or_mismatched")
    checked_date = dt.date.fromisoformat(data["pricing"]["checked_on"])
    input_date = dt.date.fromisoformat(data["input_reservation"]["checked_on"])
    today = today or dt.date.today()
    if (today - checked_date).days < 0 or (today - checked_date).days > PROFILE_FRESHNESS_DAYS:
        raise ProfileFailure("pricing_source_stale")
    if (today - input_date).days < 0 or (today - input_date).days > PROFILE_FRESHNESS_DAYS:
        raise ProfileFailure("input_source_stale")
    return ProviderProfile(
        raw=data,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        input_price=Decimal(data["pricing"]["input_peak_cache_miss_per_million"]),
        output_price=Decimal(data["pricing"]["output_peak_per_million"]),
        input_reserve_tokens=data["input_reservation"]["tokens"],
        max_output_tokens=data["max_output_tokens"],
        max_rounds=data["max_rounds"],
    )


def is_validated_profile(profile: Any) -> bool:
    if not isinstance(profile, ProviderProfile):
        return False
    try:
        current = load_profile()
    except ProfileFailure:
        return False
    # A frozen dataclass is not sufficient: callers can use dataclasses.replace
    # to change derived accounting values while retaining the pinned raw blob.
    return (
        type(profile.sha256) is str and profile.sha256 == current.sha256
        and _same_typed_value(profile.raw, EXPECTED)
        and type(profile.input_price) is Decimal and profile.input_price == current.input_price
        and type(profile.output_price) is Decimal and profile.output_price == current.output_price
        and type(profile.input_reserve_tokens) is int
        and profile.input_reserve_tokens == current.input_reserve_tokens
        and type(profile.max_output_tokens) is int and profile.max_output_tokens == current.max_output_tokens
        and type(profile.max_rounds) is int and profile.max_rounds == current.max_rounds
    )


def validate_budget_evidence(path: Path | None, *, cap_cny: Decimal = Decimal("5"),
                             today: dt.date | None = None) -> dict[str, Any]:
    if path is None:
        return {"status": "unknown", "prior_spend_cny": None, "source": None, "code": "prior_spend_missing"}
    if (path.name == ".env" or path.name.startswith(".env.") or path.is_symlink()
            or "credential" in path.name.lower() or "secret" in path.name.lower()):
        return {"status": "unknown", "prior_spend_cny": None, "source": None, "code": "budget_evidence_invalid"}
    try:
        if not path.is_file() or path.stat().st_size > 65_536:
            raise ValueError("unsupported budget evidence file")
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_without_duplicates,
                          parse_constant=lambda _s: (_ for _ in ()).throw(ValueError("constant")))
    except Exception:
        return {"status": "unknown", "prior_spend_cny": None, "source": None, "code": "budget_evidence_unreadable"}
    required = {"schema", "scope", "currency", "prior_spend_cny", "source", "checked_on"}
    if not isinstance(data, dict) or set(data) != required:
        return {"status": "unknown", "prior_spend_cny": None, "source": None, "code": "budget_evidence_invalid"}
    amount = data.get("prior_spend_cny")
    source = data.get("source")
    try:
        checked = dt.date.fromisoformat(data["checked_on"]) if isinstance(data.get("checked_on"), str) else None
    except ValueError:
        checked = None
    today = today or dt.date.today()
    valid_amount = type(amount) in (int, float) and Decimal(str(amount)).is_finite() and Decimal(str(amount)) >= 0
    valid = (
        data["schema"] == "chi-shared-budget-evidence-v1"
        and data["scope"] == "shared_B_C"
        and data["currency"] == "CNY"
        and valid_amount
        and type(cap_cny) is Decimal and cap_cny.is_finite() and cap_cny > 0
        and Decimal(str(amount)) <= cap_cny
        and isinstance(source, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", source) is not None
        and not any(word in source.lower() for word in ("synthetic", "fixture", "mock"))
        and checked is not None and 0 <= (today - checked).days <= PROFILE_FRESHNESS_DAYS
    )
    if not valid:
        return {"status": "unknown", "prior_spend_cny": None, "source": None, "code": "budget_evidence_invalid_or_stale"}
    return {"status": "known", "prior_spend_cny": str(Decimal(str(amount))), "source": source.strip(), "code": None}
