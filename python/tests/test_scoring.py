from stock_evolution_model.metrics import compute_quarter_metrics, linear_trend_slope
from stock_evolution_model.scoring import (
    grade_for_score,
    score_cash_flow,
    score_debt,
    score_profitability,
    score_revenue_growth,
    score_valuation,
)
from stock_evolution_model.types import QuarterFundamentals, ValuationSnapshot


def make_quarter(period: str, revenue: float, **overrides) -> QuarterFundamentals:
    defaults = dict(
        period=period,
        revenue=revenue,
        gross_profit=revenue * 0.5,
        operating_income=revenue * 0.2,
        net_income=revenue * 0.15,
        total_assets=revenue * 2,
        total_equity=revenue * 1.0,
        total_debt=revenue * 0.3,
        current_assets=revenue * 0.6,
        current_liabilities=revenue * 0.3,
        interest_expense=revenue * 0.01,
        ebitda=revenue * 0.25,
        operating_cash_flow=revenue * 0.18,
        capex=revenue * 0.05,
    )
    defaults.update(overrides)
    return QuarterFundamentals(**defaults)


def test_linear_trend_slope_basic():
    assert linear_trend_slope([1, 2, 3, 4]) == 1.0
    assert linear_trend_slope([4, 3, 2, 1]) == -1.0
    assert linear_trend_slope([5]) is None
    assert linear_trend_slope([]) is None


def test_grade_for_score_bounds():
    assert grade_for_score(95) == "A"
    assert grade_for_score(85) == "A"
    assert grade_for_score(84.9) == "B"
    assert grade_for_score(55) == "C"
    assert grade_for_score(39.9) == "F"


def test_revenue_growth_rewards_growing_company():
    quarters = [make_quarter(f"Q{i}", 100 * (1.1**i)) for i in range(6)]
    metrics = compute_quarter_metrics(quarters)
    result = score_revenue_growth(metrics)
    assert result.score > 50
    assert result.trend in ("Improving", "Stable")
    assert 0 <= result.score <= 100


def test_revenue_growth_penalizes_shrinking_company():
    quarters = [make_quarter(f"Q{i}", 100 * (0.9**i)) for i in range(6)]
    metrics = compute_quarter_metrics(quarters)
    result = score_revenue_growth(metrics)
    assert result.score < 50


def test_profitability_scores_within_bounds():
    quarters = [make_quarter(f"Q{i}", 100 + i * 5) for i in range(4)]
    metrics = compute_quarter_metrics(quarters)
    result = score_profitability(metrics)
    assert 0 <= result.score <= 100
    assert result.grade in ("A", "B", "C", "D", "F")


def test_debt_trend_inverted_for_rising_leverage():
    quarters = [
        make_quarter(f"Q{i}", 100, total_debt=100 * (1 + i * 0.3), total_equity=100)
        for i in range(4)
    ]
    metrics = compute_quarter_metrics(quarters)
    result = score_debt(metrics)
    assert result.trend == "Deteriorating"


def test_cash_flow_handles_single_quarter_without_crashing():
    quarters = [make_quarter("Q0", 100)]
    metrics = compute_quarter_metrics(quarters)
    result = score_cash_flow(metrics)
    assert 0 <= result.score <= 100
    assert result.trend == "Stable"


def test_valuation_prefers_lower_multiples():
    cheap = ValuationSnapshot(trailing_pe=10, peg_ratio=0.8, price_to_sales=2)
    expensive = ValuationSnapshot(trailing_pe=55, peg_ratio=3.5, price_to_sales=14)
    assert score_valuation(cheap).score > score_valuation(expensive).score


def test_valuation_handles_missing_data():
    empty = ValuationSnapshot()
    result = score_valuation(empty)
    assert result.score == 50.0
