"""AI-powered stock evolution model.

Evaluates a company's fundamental trajectory across five categories -
revenue growth, profitability, valuation, debt levels, and cash flow
trends - from quarterly financial statements, producing a weighted overall
score, letter grade, and trend direction per category and overall.
"""

from .model import StockEvolutionModel, format_report
from .types import CategoryResult, EvolutionReport

__all__ = [
    "StockEvolutionModel",
    "format_report",
    "EvolutionReport",
    "CategoryResult",
]
