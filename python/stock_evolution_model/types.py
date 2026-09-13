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
class FundamentalsSnapshot:
    symbol: str
    company_name: str
    is_demo_data: bool
    quarters: list[QuarterFundamentals]
    valuation: ValuationSnapshot
    data_notes: list[str] = field(default_factory=list)


@dataclass
class CategoryResult:
    name: str
    score: float  # 0-100
    grade: str
    trend: str  # "Improving" | "Stable" | "Deteriorating"
    metrics: dict = field(default_factory=dict)
    detail: str = ""


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

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "is_demo_data": self.is_demo_data,
            "data_notes": self.data_notes,
            "overall_score": round(self.overall_score, 1),
            "overall_grade": self.overall_grade,
            "overall_trend": self.overall_trend,
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
