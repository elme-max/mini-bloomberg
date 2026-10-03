"""Heuristic 0-100 scoring for each of the five evaluation categories.

Each `score_*` function maps a financial metric onto a 0-100 scale using
thresholds drawn from common equity-research rules of thumb. This keeps the
model transparent and explainable (every score can be traced back to a
specific metric and threshold) rather than an opaque black box.
"""

from __future__ import annotations

from .metrics import GROWTH_BASIS_QOQ, QuarterMetrics, TTMMetrics, linear_trend_slope
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


def _lower_is_better(value: float | None, worst: float, best: float) -> float | None:
    """Score a valuation/leverage multiple; None when missing or not meaningful (<= 0)."""
    if value is None or value <= 0:
        return None
    return _scale(value, worst, best)  # worst -> 0, best -> 100


def _weighted_average(parts: list[tuple[float, float]]) -> float:
    """parts = [(score, weight)]; neutral 50 when nothing could be scored."""
    total = sum(w for _, w in parts)
    if not total:
        return 50.0
    return sum(s * w for s, w in parts) / total


def score_revenue_growth(
    quarterly: list[QuarterMetrics],
    growth: float | None = None,
    basis: str | None = None,
) -> CategoryResult:
    series = [q.revenue_growth for q in quarterly if q.revenue_growth is not None]
    if growth is None and series:
        growth = series[-1]
        basis = (
            "latest quarter vs same quarter last year"
            if quarterly[-1].revenue_growth_is_yoy
            else GROWTH_BASIS_QOQ
        )
    score = _scale(growth, -0.20, 0.30) if growth is not None else 50.0
    slope = linear_trend_slope(series) if len(series) >= 2 else None

    return CategoryResult(
        name="Revenue Growth",
        score=score,
        grade=grade_for_score(score),
        trend=_trend_label(slope),
        metrics={
            "latest_growth_pct": round(growth * 100, 2) if growth is not None else None,
            "growth_basis": basis or "n/a",
            "growth_series_pct": [round(g * 100, 2) for g in series],
        },
        detail="Revenue growth scaled against a -20%..+30% band, measured on the most "
        "reliable basis available; trend from the slope of the quarterly growth series.",
    )


def score_profitability(
    quarterly: list[QuarterMetrics], ttm: TTMMetrics | None = None
) -> CategoryResult:
    net_margins = [q.net_margin for q in quarterly if q.net_margin is not None]
    if ttm is not None:
        margin, roe, basis = ttm.net_margin, ttm.roe, ttm.basis
    else:
        margin = net_margins[-1] if net_margins else None
        quarter_roe = next((q.roe for q in reversed(quarterly) if q.roe is not None), None)
        roe = quarter_roe * 4 if quarter_roe is not None else None  # annualize
        basis = "latest quarter (ROE annualized)"

    margin_score = _scale(margin, -0.05, 0.25) if margin is not None else 50.0
    roe_score = _scale(roe, 0.0, 0.30) if roe is not None else 50.0
    score = margin_score * 0.6 + roe_score * 0.4

    slope = linear_trend_slope(net_margins) if len(net_margins) >= 2 else None

    return CategoryResult(
        name="Profitability",
        score=score,
        grade=grade_for_score(score),
        trend=_trend_label(slope),
        metrics={
            "latest_net_margin_pct": round(margin * 100, 2) if margin is not None else None,
            "latest_roe_pct": round(roe * 100, 2) if roe is not None else None,
            "basis": basis,
            "net_margin_series_pct": [round(m * 100, 2) for m in net_margins],
        },
        detail="Blend of net margin (60%) and annual return on equity (40%); "
        "trend from the slope of the quarterly net-margin series.",
    )


def score_valuation(valuation: ValuationSnapshot, loss_making: bool = False) -> CategoryResult:
    # Lower multiples score higher; PEG folds growth into the P/E read.
    # Negative or missing multiples (e.g. P/E of a loss-making company) are skipped.
    candidates = {
        "peg": _lower_is_better(valuation.peg_ratio, worst=4.0, best=0.5),
        "trailing_pe": _lower_is_better(valuation.trailing_pe, worst=60.0, best=8.0),
        "forward_pe": _lower_is_better(valuation.forward_pe, worst=50.0, best=8.0),
        "ev_to_ebitda": _lower_is_better(valuation.ev_to_ebitda, worst=30.0, best=6.0),
        "price_to_sales": _lower_is_better(valuation.price_to_sales, worst=15.0, best=1.0),
    }
    components = [v for v in candidates.values() if v is not None]
    if loss_making:
        components.append(0.0)  # no earnings to anchor the valuation on
    score = sum(components) / len(components) if components else 50.0

    detail = (
        "Average of PEG, trailing P/E, forward P/E, EV/EBITDA and P/S scores "
        "(lower multiple = higher score; missing or negative multiples are skipped)."
    )
    if loss_making:
        detail += " Company is loss-making, so an extra zero-score component is included."

    return CategoryResult(
        name="Valuation",
        score=score,
        grade=grade_for_score(score),
        trend="Stable",  # valuation is a point-in-time read, not a quarterly series
        metrics={
            "trailing_pe": valuation.trailing_pe,
            "forward_pe": valuation.forward_pe,
            "peg_ratio": valuation.peg_ratio,
            "ev_to_ebitda": valuation.ev_to_ebitda,
            "price_to_sales": valuation.price_to_sales,
            "price_to_book": valuation.price_to_book,
            "loss_making": loss_making,
        },
        detail=detail,
    )


def score_debt(quarterly: list[QuarterMetrics]) -> CategoryResult:
    def latest(attr: str) -> float | None:
        return next((getattr(q, attr) for q in reversed(quarterly) if getattr(q, attr) is not None), None)

    de_ratios = [q.debt_to_equity for q in quarterly if q.debt_to_equity is not None]
    latest_de = de_ratios[-1] if de_ratios else None
    latest_current = latest("current_ratio")
    latest_coverage = latest("interest_coverage")
    latest_leverage = latest("debt_to_ebitda")

    parts: list[tuple[float, float]] = []
    if latest_de is not None:
        # Negative equity (debt-funded buybacks, accumulated losses) is the worst case.
        parts.append((0.0 if latest_de < 0 else _scale(latest_de, 3.0, 0.0), 0.40))
    if latest_current is not None:
        parts.append((_scale(latest_current, 0.5, 2.5), 0.20))
    if latest_coverage is not None:
        parts.append((_scale(latest_coverage, 1.5, 10.0), 0.20))
    if latest_leverage is not None:
        parts.append((0.0 if latest_leverage < 0 else _scale(latest_leverage, 4.0, 0.0), 0.20))
    score = _weighted_average(parts)

    slope = linear_trend_slope(de_ratios) if len(de_ratios) >= 2 else None
    # Debt going up is deteriorating, so invert the raw slope's meaning.
    trend = _trend_label(-slope if slope is not None else None)

    def r(value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    return CategoryResult(
        name="Debt Levels",
        score=score,
        grade=grade_for_score(score),
        trend=trend,
        metrics={
            "latest_debt_to_equity": r(latest_de),
            "latest_current_ratio": r(latest_current),
            "latest_interest_coverage": r(latest_coverage),
            "latest_debt_to_ebitda": r(latest_leverage),
            "debt_to_equity_series": [round(d, 2) for d in de_ratios],
        },
        detail="Weighted blend of debt/equity (40%), current ratio (20%), interest coverage "
        "(20%) and debt/EBITDA (20%); missing inputs are skipped. Negative equity scores 0. "
        "Trend is inverted so a shrinking debt/equity reads as Improving.",
    )


def score_cash_flow(
    quarterly: list[QuarterMetrics], ttm: TTMMetrics | None = None
) -> CategoryResult:
    fcf_series = [q.free_cash_flow for q in quarterly]
    if ttm is not None:
        margin, basis = ttm.fcf_margin, ttm.basis
    else:
        fcf_margins = [q.fcf_margin for q in quarterly if q.fcf_margin is not None]
        margin = fcf_margins[-1] if fcf_margins else None
        basis = "latest quarter"

    margin_score = _scale(margin, -0.10, 0.25) if margin is not None else 50.0
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
            "latest_fcf_margin_pct": round(margin * 100, 2) if margin is not None else None,
            "basis": basis,
            "free_cash_flow_series": [round(v, 0) for v in fcf_series],
        },
        detail="Free cash flow margin, adjusted by the normalized slope of the "
        "FCF series across recent quarters.",
    )
