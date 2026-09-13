"""Top-level orchestration: fetch -> derive metrics -> score -> report."""

from __future__ import annotations

from . import scoring
from .fetch import fetch_fundamentals
from .metrics import compute_quarter_metrics
from .types import EvolutionReport, FundamentalsSnapshot

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

    def analyze(self, symbol: str) -> EvolutionReport:
        snapshot = fetch_fundamentals(symbol)
        return self._build_report(snapshot)

    def analyze_snapshot(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        """Score a pre-fetched snapshot directly (useful for tests / offline data)."""
        return self._build_report(snapshot)

    def _build_report(self, snapshot: FundamentalsSnapshot) -> EvolutionReport:
        quarterly = compute_quarter_metrics(snapshot.quarters)

        categories = [
            scoring.score_revenue_growth(quarterly),
            scoring.score_profitability(quarterly),
            scoring.score_valuation(snapshot.valuation),
            scoring.score_debt(quarterly),
            scoring.score_cash_flow(quarterly),
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


def format_report(report: EvolutionReport) -> str:
    lines = [
        f"{report.company_name} ({report.symbol})",
        f"Overall: {report.overall_score:.1f}/100  Grade: {report.overall_grade}  "
        f"Trend: {report.overall_trend}",
    ]
    if report.is_demo_data:
        lines.append(f"[DEMO DATA] {'; '.join(report.data_notes)}")
    lines.append("")
    for c in report.categories:
        lines.append(f"- {c.name}: {c.score:.1f}/100 ({c.grade}), {c.trend}")
        lines.append(f"    {c.detail}")
    return "\n".join(lines)
