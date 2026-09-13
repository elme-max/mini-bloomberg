"""Derived financial metrics computed from raw quarterly fundamentals."""

from __future__ import annotations

from dataclasses import dataclass

from .types import QuarterFundamentals


def _safe_div(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


@dataclass
class QuarterMetrics:
    period: str
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    roe: float | None
    roa: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    interest_coverage: float | None
    debt_to_ebitda: float | None
    free_cash_flow: float
    fcf_margin: float | None
    revenue_growth: float | None  # YoY if 4+ prior quarters exist, else QoQ
    revenue_growth_is_yoy: bool


def compute_quarter_metrics(quarters: list[QuarterFundamentals]) -> list[QuarterMetrics]:
    results: list[QuarterMetrics] = []
    for i, q in enumerate(quarters):
        fcf = q.operating_cash_flow - q.capex

        revenue_growth = None
        is_yoy = False
        if i >= 4:
            prior = quarters[i - 4]
            revenue_growth = _safe_div(q.revenue - prior.revenue, prior.revenue)
            is_yoy = True
        elif i >= 1:
            prior = quarters[i - 1]
            revenue_growth = _safe_div(q.revenue - prior.revenue, prior.revenue)
            is_yoy = False

        results.append(
            QuarterMetrics(
                period=q.period,
                gross_margin=_safe_div(q.gross_profit, q.revenue),
                operating_margin=_safe_div(q.operating_income, q.revenue),
                net_margin=_safe_div(q.net_income, q.revenue),
                roe=_safe_div(q.net_income, q.total_equity),
                roa=_safe_div(q.net_income, q.total_assets),
                debt_to_equity=_safe_div(q.total_debt, q.total_equity),
                current_ratio=_safe_div(q.current_assets, q.current_liabilities),
                interest_coverage=_safe_div(q.operating_income, q.interest_expense),
                debt_to_ebitda=_safe_div(q.total_debt, q.ebitda),
                free_cash_flow=fcf,
                fcf_margin=_safe_div(fcf, q.revenue),
                revenue_growth=revenue_growth,
                revenue_growth_is_yoy=is_yoy,
            )
        )
    return results


def linear_trend_slope(values: list[float]) -> float | None:
    """Least-squares slope of `values` against their index (0, 1, 2, ...).

    A small, dependency-free stand-in for a regression-based trend model:
    positive slope means the metric is improving quarter over quarter,
    negative means it's deteriorating. Returns None with fewer than 2 points.
    """

    n = len(values)
    if n < 2:
        return None

    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return numerator / denominator
