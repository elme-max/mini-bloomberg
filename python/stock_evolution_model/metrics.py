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


def _annualized_ebitda(quarters: list[QuarterFundamentals], index: int) -> float:
    """Trailing-four-quarter EBITDA ending at `index` (scaled up if <4 quarters)."""
    window = quarters[max(0, index - 3) : index + 1]
    return sum(q.ebitda for q in window) * 4 / len(window)


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
                debt_to_ebitda=_safe_div(q.total_debt, _annualized_ebitda(quarters, i)),
                free_cash_flow=fcf,
                fcf_margin=_safe_div(fcf, q.revenue),
                revenue_growth=revenue_growth,
                revenue_growth_is_yoy=is_yoy,
            )
        )
    return results


GROWTH_BASIS_QOQ = "QoQ (seasonal, less reliable)"


def best_revenue_growth(
    quarters: list[QuarterFundamentals], annual: list[QuarterFundamentals]
) -> tuple[float | None, str]:
    """Most reliable revenue growth available, plus a label saying how it was measured.

    Preference: trailing-12-month vs the prior 12 months, then the latest
    quarter vs the same quarter a year earlier, then fiscal-year vs prior
    fiscal year, and only as a last resort quarter-over-quarter (which is
    distorted by seasonality).
    """

    n = len(quarters)
    if n >= 8:
        recent = sum(q.revenue for q in quarters[-4:])
        prior = sum(q.revenue for q in quarters[-8:-4])
        growth = _safe_div(recent - prior, prior)
        if growth is not None:
            return growth, "last 12 months vs prior 12 months"
    if n >= 5:
        growth = _safe_div(quarters[-1].revenue - quarters[-5].revenue, quarters[-5].revenue)
        if growth is not None:
            return growth, "latest quarter vs same quarter last year"
    if len(annual) >= 2:
        growth = _safe_div(annual[-1].revenue - annual[-2].revenue, annual[-2].revenue)
        if growth is not None:
            return growth, "latest fiscal year vs prior year"
    if n >= 2:
        growth = _safe_div(quarters[-1].revenue - quarters[-2].revenue, quarters[-2].revenue)
        if growth is not None:
            return growth, GROWTH_BASIS_QOQ
    return None, "n/a"


@dataclass
class TTMMetrics:
    """Trailing-twelve-month profitability and cash flow (annualized if <4 quarters)."""

    net_income: float
    net_margin: float | None
    roe: float | None  # annualized net income / latest equity
    fcf_margin: float | None
    quarters_used: int
    source: str = ""  # set when figures come from the data source rather than the statements

    @property
    def basis(self) -> str:
        if self.source:
            return self.source
        if self.quarters_used >= 4:
            return "trailing 12 months"
        return f"annualized from {self.quarters_used} quarter(s)"


def compute_ttm(quarters: list[QuarterFundamentals]) -> TTMMetrics | None:
    window = quarters[-4:]
    if not window:
        return None
    revenue = sum(q.revenue for q in window)
    net_income = sum(q.net_income for q in window)
    fcf = sum(q.operating_cash_flow - q.capex for q in window)
    annualization = 4 / len(window)
    return TTMMetrics(
        net_income=net_income * annualization,
        net_margin=_safe_div(net_income, revenue),
        roe=_safe_div(net_income * annualization, window[-1].total_equity),
        fcf_margin=_safe_div(fcf, revenue),
        quarters_used=len(window),
    )


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
