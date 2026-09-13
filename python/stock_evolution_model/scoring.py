"""Heuristic 0-100 scoring for each of the five evaluation categories.

Each `normalize_*` function maps a financial metric onto a 0-100 scale using
thresholds drawn from common equity-research rules of thumb. This keeps the
model transparent and explainable (every score can be traced back to a
specific metric and threshold) rather than an opaque black box.
"""

from __future__ import annotations

from .metrics import QuarterMetrics, linear_trend_slope
from .types import CategoryResult, ValuationSnapshot

TREND_FLAT_THRESHOLD = 0.01  # slope magnitude below this counts as "Stable"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scale(value: float, low: float, high: float) -> float:
    """Linearly map value in [low, high] to [0, 100], clamped at the ends."""
    if high == low:
        return 50.0
    return _clamp((value - low) / (high - low) * 100)


def grade_for_score(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _trend_label(slope: float | None) -> str:
    if slope is None:
        return "Stable"
    if slope > TREND_FLAT_THRESHOLD:
        return "Improving"
    if slope < -TREND_FLAT_THRESHOLD:
        return "Deteriorating"
    return "Stable"


def score_revenue_growth(quarterly: list[QuarterMetrics]) -> CategoryResult:
    growths = [q.revenue_growth for q in quarterly if q.revenue_growth is not None]
    latest = growths[-1] if growths else None
    score = _scale(latest, -0.20, 0.30) if latest is not None else 50.0
    slope = linear_trend_slope(growths) if len(growths) >= 2 else None

    return CategoryResult(
        name="Revenue Growth",
        score=score,
        grade=grade_for_score(score),
        trend=_trend_label(slope),
        metrics={
            "latest_growth_pct": round(latest * 100, 2) if latest is not None else None,
            "growth_is_yoy": quarterly[-1].revenue_growth_is_yoy if quarterly else None,
            "growth_series_pct": [round(g * 100, 2) for g in growths],
        },
        detail="Latest revenue growth scaled against a -20%..+30% band; "
        "trend from the slope of the growth-rate series.",
    )


def score_profitability(quarterly: list[QuarterMetrics]) -> CategoryResult:
    net_margins = [q.net_margin for q in quarterly if q.net_margin is not None]
    roes = [q.roe for q in quarterly if q.roe is not None]
    latest_margin = net_margins[-1] if net_margins else None
    latest_roe = roes[-1] if roes else None

    margin_score = _scale(latest_margin, -0.05, 0.25) if latest_margin is not None else 50.0
    roe_score = _scale(latest_roe, 0.0, 0.30) if latest_roe is not None else 50.0
    score = margin_score * 0.6 + roe_score * 0.4

    slope = linear_trend_slope(net_margins) if len(net_margins) >= 2 else None

    return CategoryResult(
        name="Profitability",
        score=score,
        grade=grade_for_score(score),
        trend=_trend_label(slope),
        metrics={
            "latest_net_margin_pct": round(latest_margin * 100, 2) if latest_margin is not None else None,
            "latest_roe_pct": round(latest_roe * 100, 2) if latest_roe is not None else None,
            "net_margin_series_pct": [round(m * 100, 2) for m in net_margins],
        },
        detail="Blend of net margin (60%) and return on equity (40%); "
        "trend from the slope of the net-margin series.",
    )


def score_valuation(valuation: ValuationSnapshot) -> CategoryResult:
    # Lower multiples score higher; PEG folds growth into the P/E read.
    peg_score = _scale(-(valuation.peg_ratio), -4.0, -0.5) if valuation.peg_ratio else None
    pe_score = _scale(-(valuation.trailing_pe), -60.0, -8.0) if valuation.trailing_pe else None
    ps_score = _scale(-(valuation.price_to_sales), -15.0, -1.0) if valuation.price_to_sales else None

    components = [s for s in (peg_score, pe_score, ps_score) if s is not None]
    score = sum(components) / len(components) if components else 50.0

    return CategoryResult(
        name="Valuation",
        score=score,
        grade=grade_for_score(score),
        trend="Stable",  # valuation is a point-in-time read, not a quarterly series
        metrics={
            "trailing_pe": valuation.trailing_pe,
            "forward_pe": valuation.forward_pe,
            "peg_ratio": valuation.peg_ratio,
            "price_to_sales": valuation.price_to_sales,
            "price_to_book": valuation.price_to_book,
            "ev_to_ebitda": valuation.ev_to_ebitda,
        },
        detail="Average of PEG, trailing P/E and P/S scores (lower multiple = higher score).",
    )


def score_debt(quarterly: list[QuarterMetrics]) -> CategoryResult:
    de_ratios = [q.debt_to_equity for q in quarterly if q.debt_to_equity is not None]
    current_ratios = [q.current_ratio for q in quarterly if q.current_ratio is not None]
    latest_de = de_ratios[-1] if de_ratios else None
    latest_current = current_ratios[-1] if current_ratios else None

    de_score = _scale(-(latest_de), -3.0, 0.0) if latest_de is not None else 50.0
    current_score = _scale(latest_current, 0.5, 2.5) if latest_current is not None else 50.0
    score = de_score * 0.65 + current_score * 0.35

    slope = linear_trend_slope(de_ratios) if len(de_ratios) >= 2 else None
    # Debt going up is deteriorating, so invert the raw slope's meaning.
    trend = _trend_label(-slope if slope is not None else None)

    return CategoryResult(
        name="Debt Levels",
        score=score,
        grade=grade_for_score(score),
        trend=trend,
        metrics={
            "latest_debt_to_equity": round(latest_de, 2) if latest_de is not None else None,
            "latest_current_ratio": round(latest_current, 2) if latest_current is not None else None,
            "debt_to_equity_series": [round(d, 2) for d in de_ratios],
        },
        detail="Blend of debt/equity (65%) and current ratio (35%); "
        "trend is inverted so a shrinking debt/equity reads as Improving.",
    )


def score_cash_flow(quarterly: list[QuarterMetrics]) -> CategoryResult:
    fcf_series = [q.free_cash_flow for q in quarterly]
    fcf_margins = [q.fcf_margin for q in quarterly if q.fcf_margin is not None]
    latest_margin = fcf_margins[-1] if fcf_margins else None

    margin_score = _scale(latest_margin, -0.10, 0.25) if latest_margin is not None else 50.0
    slope = linear_trend_slope(fcf_series) if len(fcf_series) >= 2 else None
    # Normalize slope by average absolute FCF so the trend bonus is scale-free.
    avg_abs_fcf = sum(abs(v) for v in fcf_series) / len(fcf_series) if fcf_series else 0
    normalized_slope = (slope / avg_abs_fcf) if slope is not None and avg_abs_fcf else None
    trend_bonus = _clamp((normalized_slope or 0.0) * 200, -20, 20)

    score = _clamp(margin_score + trend_bonus)

    return CategoryResult(
        name="Cash Flow Trends",
        score=score,
        grade=grade_for_score(score),
        trend=_trend_label(normalized_slope),
        metrics={
            "latest_fcf_margin_pct": round(latest_margin * 100, 2) if latest_margin is not None else None,
            "free_cash_flow_series": [round(v, 0) for v in fcf_series],
        },
        detail="Free cash flow margin, adjusted by the normalized slope of the "
        "FCF series across recent quarters.",
    )
