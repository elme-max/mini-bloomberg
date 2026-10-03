"""Shared data structures for the AI-powered stock evolution model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuarterFundamentals:
    """Raw fundamentals for a single fiscal quarter, oldest-to-newest ordering."""

    period: str
    revenue: float
    gross_profit: float
    operating_income: float
    net_income: float
    total_assets: float
    total_equity: float
    total_debt: float
    current_assets: float
    current_liabilities: float
    interest_expense: float
    ebitda: float
    operating_cash_flow: float
    capex: float


@dataclass
class ValuationSnapshot:
    share_price: Optional[float] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    ev_to_ebitda: Optional[float] = None


@dataclass
class ReportedMetrics:
    """Headline figures exactly as the data source (Yahoo Finance) publishes them.

    These are the "current" numbers people compare against on the Yahoo page,
    so they take precedence over this model's own statement-based calculation
    when present. All ratios are plain fractions/multiples (25% -> 0.25).
    """

    revenue_growth: Optional[float] = None  # latest quarter vs same quarter last year
    net_margin: Optional[float] = None  # trailing 12 months
    roe: Optional[float] = None  # trailing 12 months
    debt_to_equity: Optional[float] = None  # most recent quarter, as a multiple
    current_ratio: Optional[float] = None  # most recent quarter
    fcf_margin: Optional[float] = None  # trailing-12-month FCF / revenue


@dataclass
class FundamentalsSnapshot:
    symbol: str
    company_name: str
    is_demo_data: bool
    quarters: list[QuarterFundamentals]
    valuation: ValuationSnapshot
    data_notes: list[str] = field(default_factory=list)
    # Fiscal-year statements (oldest-to-newest); used when too few quarters
    # exist for a same-quarter-last-year growth comparison.
    annual: list[QuarterFundamentals] = field(default_factory=list)
    sector: Optional[str] = None  # as reported by the data source, e.g. "Technology"
    reported: ReportedMetrics = field(default_factory=ReportedMetrics)


@dataclass
class CategoryResult:
    name: str
    score: float  # 0-100
    grade: str
    trend: str  # "Improving" | "Stable" | "Deteriorating"
    metrics: dict = field(default_factory=dict)
    detail: str = ""


@dataclass
class SourceComparison:
    """One metric: this model's own calculation next to the data source's figure."""

    metric: str
    unit: str  # "%" or "x"
    computed: Optional[float]  # as a fraction/multiple, like ReportedMetrics
    reported: Optional[float]
    used: str  # "reported" or "computed": which value the scoring used

    def rounded(self, value: Optional[float]) -> Optional[float]:
        """2 decimals as displayed: 4 places for a fraction (18.23%), 2 for a multiple."""
        if value is None:
            return None
        return round(value, 4 if self.unit == "%" else 2)

    @property
    def difference(self) -> Optional[float]:
        if self.computed is None or self.reported is None:
            return None
        return self.computed - self.reported


@dataclass
class EvolutionReport:
    symbol: str
    company_name: str
    is_demo_data: bool
    data_notes: list[str]
    categories: list[CategoryResult]
    overall_score: float
    overall_grade: str
    overall_trend: str
    sector: Optional[str] = None
    sector_profile: str = "Generic"  # name of the scoring profile that was applied
    comparisons: list[SourceComparison] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "is_demo_data": self.is_demo_data,
            "data_notes": self.data_notes,
            "overall_score": round(self.overall_score, 1),
            "overall_grade": self.overall_grade,
            "overall_trend": self.overall_trend,
            "sector": self.sector,
            "sector_profile": self.sector_profile,
            "source_comparison": [
                {
                    "metric": c.metric,
                    "unit": c.unit,
                    "computed": c.rounded(c.computed),
                    "reported": c.rounded(c.reported),
                    "difference": c.rounded(c.difference),
                    "used": c.used,
                }
                for c in self.comparisons
            ],
            "categories": [
                {
                    "name": c.name,
                    "score": round(c.score, 1),
                    "grade": c.grade,
                    "trend": c.trend,
                    "metrics": c.metrics,
                    "detail": c.detail,
                }
                for c in self.categories
            ],
        }
