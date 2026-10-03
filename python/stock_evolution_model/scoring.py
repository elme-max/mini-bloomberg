"""Heuristic 0-100 scoring for each of the five evaluation categories.

Each `score_*` function maps a financial metric onto a 0-100 scale using the
bands of a `SectorProfile` (see `sectors.py`), which default to generic
equity-research rules of thumb. This keeps the model transparent and
explainable (every score can be traced back to a specific metric and band)
rather than an opaque black box.
"""

from __future__ import annotations

from .metrics import GROWTH_BASIS_QOQ, QuarterMetrics, TTMMetrics, linear_trend_slope
from .sectors import GENERIC, Band, SectorProfile
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


def _round2(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _band_score(value: float | None, band: Band | None) -> float | None:
    """0-100 score of `value` within `band`; None if the value or band is missing."""
    if value is None or band is None:
        return None
    return _scale(value, band[0], band[1])


def _multiple_score(value: float | None, band: Band | None) -> float | None:
    """Like `_band_score` for valuation multiples, ignoring non-positive values."""
    if value is None or value <= 0:
        return None
    return _band_score(value, band)


def _weighted_average(parts: list[tuple[float, float]]) -> float:
    """parts = [(score, weight)]; neutral 50 when nothing could be scored."""
    total = sum(w for _, w in parts)
    if not total:
        return 50.0
    return sum(s * w for s, w in parts) / total


def _pct(band: Band | None) -> str:
    return "n/a" if band is None else f"0 pts at {band[0]:+.0%}, 100 pts at {band[1]:+.0%}"


def _num(band: Band | None) -> str:
    return "n/a" if band is None else f"0 pts at {band[0]:g}x, 100 pts at {band[1]:g}x"


def score_revenue_growth(
    quarterly: list[QuarterMetrics],
    growth: float | None = None,
    basis: str | None = None,
    profile: SectorProfile = GENERIC,
) -> CategoryResult:
    series = [q.revenue_growth for q in quarterly if q.revenue_growth is not None]
    if growth is None and series:
        growth = series[-1]
        basis = (
            "latest quarter vs same quarter last year"
            if quarterly[-1].revenue_growth_is_yoy
            else GROWTH_BASIS_QOQ
        )
    score = _band_score(growth, profile.growth)
    score = 50.0 if score is None else score
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
        detail=f"Revenue growth on the {profile.name} scale ({_pct(profile.growth)}), "
        "measured on the most reliable basis available; "
        "trend from the slope of the quarterly growth series.",
    )


def score_profitability(
    quarterly: list[QuarterMetrics],
    ttm: TTMMetrics | None = None,
    profile: SectorProfile = GENERIC,
) -> CategoryResult:
    net_margins = [q.net_margin for q in quarterly if q.net_margin is not None]
    if ttm is not None:
        margin, roe, basis = ttm.net_margin, ttm.roe, ttm.basis
    else:
        margin = net_margins[-1] if net_margins else None
        quarter_roe = next((q.roe for q in reversed(quarterly) if q.roe is not None), None)
        roe = quarter_roe * 4 if quarter_roe is not None else None  # annualize
        basis = "latest quarter (ROE annualized)"

    margin_score = _band_score(margin, profile.net_margin)
    roe_score = _band_score(roe, profile.roe)
    parts = [(sc, w) for sc, w in ((margin_score, 0.6), (roe_score, 0.4)) if sc is not None]
    score = _weighted_average(parts)

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
        detail=f"{profile.name} scale. Net margin (60%): {_pct(profile.net_margin)}. "
        f"Annual return on equity (40%): {_pct(profile.roe)}. "
        "Trend from the slope of the quarterly net-margin series.",
    )


def score_valuation(
    valuation: ValuationSnapshot,
    loss_making: bool = False,
    profile: SectorProfile = GENERIC,
) -> CategoryResult:
    # Lower multiples score higher; PEG folds growth into the P/E read.
    # Negative or missing multiples (e.g. P/E of a loss-making company) are skipped,
    # as are multiples the sector profile marks as not meaningful.
    candidates = [
        _multiple_score(valuation.peg_ratio, profile.peg),
        _multiple_score(valuation.trailing_pe, profile.trailing_pe),
        _multiple_score(valuation.forward_pe, profile.forward_pe),
        _multiple_score(valuation.ev_to_ebitda, profile.ev_to_ebitda),
        _multiple_score(valuation.price_to_sales, profile.price_to_sales),
        _multiple_score(valuation.price_to_book, profile.price_to_book),
    ]
    components = [v for v in candidates if v is not None]
    if loss_making:
        components.append(0.0)  # no earnings to anchor the valuation on
    score = sum(components) / len(components) if components else 50.0

    detail = (
        f"Average of the {profile.name} PEG, trailing P/E, forward P/E, EV/EBITDA, P/S "
        "(and P/B where the sector uses it) scores; lower multiple = higher score; "
        "missing, negative or sector-irrelevant multiples are skipped."
    )
    if loss_making:
        detail += " Company is loss-making, so an extra zero-score component is included."

    return CategoryResult(
        name="Valuation",
        score=score,
        grade=grade_for_score(score),
        trend="Stable",  # valuation is a point-in-time read, not a quarterly series
        metrics={
            "trailing_pe": _round2(valuation.trailing_pe),
            "forward_pe": _round2(valuation.forward_pe),
            "peg_ratio": _round2(valuation.peg_ratio),
            "ev_to_ebitda": _round2(valuation.ev_to_ebitda),
            "price_to_sales": _round2(valuation.price_to_sales),
            "price_to_book": _round2(valuation.price_to_book),
            "loss_making": loss_making,
        },
        detail=detail,
    )


def score_debt(
    quarterly: list[QuarterMetrics],
    profile: SectorProfile = GENERIC,
    reported_de: float | None = None,
    reported_current: float | None = None,
) -> CategoryResult:
    def latest(attr: str) -> float | None:
        return next((getattr(q, attr) for q in reversed(quarterly) if getattr(q, attr) is not None), None)

    de_ratios = [q.debt_to_equity for q in quarterly if q.debt_to_equity is not None]
    # The data source's own most-recent-quarter figures win over our calculation.
    latest_de = reported_de if reported_de is not None else (de_ratios[-1] if de_ratios else None)
    latest_current = reported_current if reported_current is not None else latest("current_ratio")
    latest_coverage = latest("interest_coverage")
    latest_leverage = latest("debt_to_ebitda")

    def leverage_score(value: float | None, band: Band | None) -> float | None:
        # Negative equity / negative EBITDA is the worst case, not a "low" ratio.
        if value is not None and value < 0 and band is not None:
            return 0.0
        return _band_score(value, band)

    candidates = [
        (leverage_score(latest_de, profile.debt_to_equity), 0.40),
        (_band_score(latest_current, profile.current_ratio), 0.20),
        (_band_score(latest_coverage, profile.interest_coverage), 0.20),
        (leverage_score(latest_leverage, profile.debt_to_ebitda), 0.20),
    ]
    score = _weighted_average([(sc, w) for sc, w in candidates if sc is not None])

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
            "latest_current_ratio": r(latest_current) if profile.current_ratio else None,
            "latest_interest_coverage": r(latest_coverage) if profile.interest_coverage else None,
            "latest_debt_to_ebitda": r(latest_leverage) if profile.debt_to_ebitda else None,
            "debt_to_equity_series": [round(d, 2) for d in de_ratios],
            "basis": "Yahoo reported D/E and current ratio"
            if reported_de is not None and reported_current is not None
            else "Yahoo reported where available, else computed"
            if reported_de is not None or reported_current is not None
            else "computed from statements",
        },
        detail=f"{profile.name} scale. Debt/equity (40%): {_num(profile.debt_to_equity)}. "
        "Also current ratio (20%), interest coverage (20%) and debt/EBITDA (20%); inputs that are "
        "missing or not meaningful for the sector show n/a and are skipped. Negative equity "
        "scores 0. Trend is inverted so a shrinking debt/equity reads as Improving.",
    )


def score_cash_flow(
    quarterly: list[QuarterMetrics],
    ttm: TTMMetrics | None = None,
    profile: SectorProfile = GENERIC,
) -> CategoryResult:
    fcf_series = [q.free_cash_flow for q in quarterly]
    if ttm is not None:
        margin, basis = ttm.fcf_margin, ttm.basis
    else:
        fcf_margins = [q.fcf_margin for q in quarterly if q.fcf_margin is not None]
        margin = fcf_margins[-1] if fcf_margins else None
        basis = "latest quarter"

    margin_score = _band_score(margin, profile.fcf_margin)
    margin_score = 50.0 if margin_score is None else margin_score
    slope = linear_trend_slope(fcf_series) if len(fcf_series) >= 2 else None
    # Normalize slope by average absolute FCF so the trend bonus is scale-free.
    avg_abs_fcf = sum(abs(v) for v in fcf_series) / len(fcf_series) if fcf_series else 0
    normalized_slope = (slope / avg_abs_fcf) if slope is not None and avg_abs_fcf else None
    trend_bonus = _clamp((normalized_slope or 0.0) * 200, -20, 20)

    score = _clamp(margin_score + trend_bonus)

    if profile.fcf_margin is None:
        # Operating cash flow isn't comparable for this sector (e.g. banks), so
        # neither the margin nor its trend says anything useful.
        score = 50.0
        detail = (f"Free cash flow isn't a meaningful yardstick for {profile.name}, "
                  "so this category is scored neutral (50).")
        trend = "Stable"
    else:
        detail = (f"Free cash flow margin on the {profile.name} scale ({_pct(profile.fcf_margin)}), "
                  "adjusted by the normalized slope of the FCF series across recent quarters.")
        trend = _trend_label(normalized_slope)

    return CategoryResult(
        name="Cash Flow Trends",
        score=score,
        grade=grade_for_score(score),
        trend=trend,
        metrics={
            "latest_fcf_margin_pct": round(margin * 100, 2) if margin is not None else None,
            "basis": basis,
            "free_cash_flow_series": [round(v, 0) for v in fcf_series],
        },
        detail=detail,
    )
