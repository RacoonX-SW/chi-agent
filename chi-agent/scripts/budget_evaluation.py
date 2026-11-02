"""Pure legacy budget evaluation shared by packaged and development adapters."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def evaluate_budget(
    budget_cny: float,
    max_rounds: int,
    max_tokens_per_request: int,
    *,
    rounds_used: int = 0,
    cumulative_cost_cny: float | int | None = None,
    input_price_usd_per_million: float | int | None = None,
    output_price_usd_per_million: float | int | None = None,
    max_input_tokens_per_request: int | None = None,
    usd_to_cny: float | int | None = None,
    pricing_version: str | None = None,
    fx_rate_source: str | None = None,
) -> tuple[str, str]:
    """Decide whether one more request can fit a measured CNY budget.

    Cumulative cost must come from measured usage already converted to CNY. The
    next-request reserve uses maximum input/output tokens and a versioned USD
    price list plus an identified USD-to-CNY rate. Missing evidence is a stop,
    never an implicit zero. The current wrapper has no trusted runtime source for
    these measurements, so its production preflight intentionally stops.
    """
    def decimal_value(value: float | int | None, *, allow_zero: bool) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError, OverflowError):
            return None
        if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
            return None
        return result

    cap = decimal_value(budget_cny, allow_zero=False)
    if cap is None:
        return "stopped_invalid_budget", "Budget cap is missing, non-finite, or non-positive"
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds <= 0:
        return "stopped_invalid_limits", "max_rounds must be a positive integer"
    if isinstance(rounds_used, bool) or not isinstance(rounds_used, int) or rounds_used < 0:
        return "stopped_invalid_usage", "rounds_used must be a non-negative integer"
    if rounds_used >= max_rounds:
        return "stopped_round_limit", f"Round limit exhausted ({rounds_used}/{max_rounds})"
    if isinstance(max_tokens_per_request, bool) or not isinstance(max_tokens_per_request, int) or max_tokens_per_request <= 0:
        return "stopped_invalid_limits", "max_tokens_per_request must be a positive integer"
    if isinstance(max_input_tokens_per_request, bool) or not isinstance(max_input_tokens_per_request, int) or max_input_tokens_per_request is None or max_input_tokens_per_request <= 0:
        return "unverified_unknown_usage", "Maximum input tokens for a request are unknown; conservative reservation cannot be computed"

    cumulative = decimal_value(cumulative_cost_cny, allow_zero=True)
    if cumulative is None:
        return "unverified_unknown_usage", "Measured cumulative cost in CNY is unavailable or invalid"
    input_price = decimal_value(input_price_usd_per_million, allow_zero=True)
    output_price = decimal_value(output_price_usd_per_million, allow_zero=True)
    fx = decimal_value(usd_to_cny, allow_zero=False)
    if input_price is None or output_price is None or not pricing_version:
        return "unverified_unknown_pricing", "Request pricing or its version is unavailable or invalid"
    if fx is None or not fx_rate_source:
        return "unverified_unknown_conversion", "USD-to-CNY conversion rate or its source is unavailable or invalid"

    reserve_usd = (
        Decimal(max_input_tokens_per_request) * input_price
        + Decimal(max_tokens_per_request) * output_price
    ) / Decimal(1_000_000)
    reserve_cny = reserve_usd * fx
    if not reserve_cny.is_finite() or reserve_cny < 0:
        return "stopped_invalid_reservation", "Computed next-request reservation is invalid"
    projected = cumulative + reserve_cny
    if not projected.is_finite():
        return "stopped_invalid_reservation", "Projected cumulative cost is invalid"
    if cumulative > cap:
        return "stopped_budget_exhausted", f"Measured cumulative cost {cumulative} CNY already exceeds cap {cap} CNY"
    if projected > cap:
        return "stopped_insufficient_budget", f"Next-request reserve would bring cumulative cost to {projected} CNY above cap {cap} CNY"
    return "within_budget", f"Measured cumulative cost {cumulative} CNY plus conservative next-request reserve {reserve_cny} CNY fits cap {cap} CNY (pricing {pricing_version}; FX {fx_rate_source})"
