"""Top-level orchestration: fetch -> derive metrics -> score -> report."""

from __future__ import annotations

from . import scoring
from .fetch import fetch_fundamentals
from .metrics import best_revenue_growth, compute_quarter_metrics, compute_ttm
from .types import CategoryResult, EvolutionReport, FundamentalsSnapshot

DEFAULT_WEIGHTS = {
    "Revenue Growth": 0.20,
    "Profitability": 0.20,
    "Valuation": 0.20,
    "Debt Levels": 0.20,
    "Cash Flow Trends": 0.20,
}


class StockEvolutionModel:
    """AI-powered multi-factor model for evaluating a company's fundamental trajectory.

    Scores five categories - revenue growth, profitability, valuation,
    debt levels, and cash flow trends - each 0-100, from up to eight
    quarters of fundamentals, then combines them into a weighted overall
    score, letter grade, and trend direction.
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("weights must sum to a positive number")
        self.weights = {k: v / total for k, v in self.weights.items()}

    def analyze(self, symbol: str, demo: bool = False) -> EvolutionReport:
        """Fetch live data and score it.

        Raises `DataUnavailableError` if live data can't be fetched; pass
        `demo=True` to score deterministic synthetic data instead.
        """
        snapshot = fetch_fundamentals(symbol, demo=demo)
        return self._build_report(snapshot)

    def analyze_snapshot(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        """Score a pre-fetched snapshot directly (useful for tests / offline data)."""
        return self._build_report(snapshot)

    def _build_report(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        quarterly = compute_quarter_metrics(snapshot.quarters)
        ttm = compute_ttm(snapshot.quarters)
        growth, growth_basis = best_revenue_growth(snapshot.quarters, snapshot.annual)
        loss_making = ttm is not None and ttm.net_income < 0

        categories = [
            scoring.score_revenue_growth(quarterly, growth, growth_basis),
            scoring.score_profitability(quarterly, ttm),
            scoring.score_valuation(snapshot.valuation, loss_making),
            scoring.score_debt(quarterly),
            scoring.score_cash_flow(quarterly, ttm),
        ]

        overall_score = sum(c.score * self.weights[c.name] for c in categories)

        trend_votes = {"Improving": 0, "Stable": 0, "Deteriorating": 0}
        for c in categories:
            trend_votes[c.trend] += 1
        overall_trend = max(trend_votes, key=lambda k: (trend_votes[k], k == "Stable"))

        return EvolutionReport(
            symbol=snapshot.symbol,
            company_name=snapshot.company_name,
            is_demo_data=snapshot.is_demo_data,
            data_notes=snapshot.data_notes,
            categories=categories,
            overall_score=overall_score,
            overall_grade=scoring.grade_for_score(overall_score),
            overall_trend=overall_trend,
        )


TREND_ICON = {"Improving": "^", "Stable": "-", "Deteriorating": "v"}

# Which metrics to surface as headline numbers under each category, and how
# to render them. (label, metrics_key, suffix) - suffix "%" appends a
# percent sign, "x" a multiple, "s" a text value, "" the raw number.
_HEADLINE_METRICS: dict[str, list[tuple[str, str, str]]] = {
    "Revenue Growth": [
        ("Growth", "latest_growth_pct", "%"),
        ("Measured as", "growth_basis", "s"),
    ],
    "Profitability": [
        ("Net margin", "latest_net_margin_pct", "%"),
        ("ROE", "latest_roe_pct", "%"),
        ("Basis", "basis", "s"),
    ],
    "Valuation": [
        ("Trailing P/E", "trailing_pe", "x"),
        ("Forward P/E", "forward_pe", "x"),
        ("PEG", "peg_ratio", ""),
        ("EV/EBITDA", "ev_to_ebitda", "x"),
        ("P/S", "price_to_sales", "x"),
    ],
    "Debt Levels": [
        ("Debt/Equity", "latest_debt_to_equity", ""),
        ("Current ratio", "latest_current_ratio", ""),
        ("Interest cover", "latest_interest_coverage", "x"),
        ("Debt/EBITDA", "latest_debt_to_ebitda", "x"),
    ],
    "Cash Flow Trends": [
        ("FCF margin", "latest_fcf_margin_pct", "%"),
        ("Basis", "basis", "s"),
    ],
}


def _format_headline(category: CategoryResult) -> str:
    parts = []
    for label, key, suffix in _HEADLINE_METRICS.get(category.name, []):
        value = category.metrics.get(key)
        if value is None:
            parts.append(f"{label}: n/a")
        elif suffix == "s":
            parts.append(f"{label}: {value}")
        elif suffix == "%":
            parts.append(f"{label}: {value:+.1f}%")
        elif suffix == "x":
            parts.append(f"{label}: {value:.1f}x")
        else:
            parts.append(f"{label}: {value:.2f}")
    return "  |  ".join(parts)


def format_report(report: EvolutionReport) -> str:
    lines = [
        f"{report.company_name} ({report.symbol})",
        f"OVERALL SCORE: {report.overall_score:.1f}/100 (Grade {report.overall_grade})  "
        f"-  Trend: {report.overall_trend}",
    ]
    if report.is_demo_data:
        lines.append(f"[DEMO DATA - not real market data] {'; '.join(report.data_notes)}")
    lines.append("")
    for c in report.categories:
        icon = TREND_ICON.get(c.trend, "-")
        lines.append(f"[{c.grade}] {c.name}: {c.score:.0f}/100  ({icon} {c.trend})")
        headline = _format_headline(c)
        if headline:
            lines.append(f"      {headline}")
        lines.append(f"      how it's scored: {c.detail}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
