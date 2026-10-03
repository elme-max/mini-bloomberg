import pytest

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


# --- growth basis, TTM, valuation and debt improvements ---------------------


def test_best_revenue_growth_prefers_ttm_then_yoy_then_annual_then_qoq():
    from stock_evolution_model.metrics import best_revenue_growth

    def qs(n):
        return [make_quarter(f"Q{i}", 100 * (1.02**i)) for i in range(n)]

    assert best_revenue_growth(qs(8), [])[1] == "last 12 months vs prior 12 months"
    assert best_revenue_growth(qs(5), [])[1] == "latest quarter vs same quarter last year"
    annual = [make_quarter("FY1", 400), make_quarter("FY2", 440)]
    growth, basis = best_revenue_growth(qs(4), annual)
    assert basis == "latest fiscal year vs prior year"
    assert growth == pytest.approx(0.10)
    assert "QoQ" in best_revenue_growth(qs(4), [])[1]
    assert best_revenue_growth(qs(1), []) == (None, "n/a")


def test_ttm_roe_is_annualized():
    from stock_evolution_model.metrics import compute_ttm

    # 4 quarters, each net income 10 on revenue 100, equity 200 -> ROE 40/200 = 20%
    quarters = [make_quarter(f"Q{i}", 100, net_income=10, total_equity=200) for i in range(4)]
    ttm = compute_ttm(quarters)
    assert ttm.roe == pytest.approx(0.20)
    assert ttm.net_margin == pytest.approx(0.10)
    assert ttm.basis == "trailing 12 months"

    # With only 2 quarters the same company must still read as 20% annual ROE.
    assert compute_ttm(quarters[:2]).roe == pytest.approx(0.20)
    assert "annualized" in compute_ttm(quarters[:2]).basis


def test_debt_to_ebitda_uses_annualized_ebitda():
    quarters = [make_quarter(f"Q{i}", 100, total_debt=100, ebitda=25) for i in range(4)]
    metrics = compute_quarter_metrics(quarters)
    # annual EBITDA = 100, debt = 100 -> 1.0x (not 4.0x from one quarter's EBITDA)
    assert metrics[-1].debt_to_ebitda == pytest.approx(1.0)


def test_valuation_uses_forward_pe_and_ev_ebitda():
    cheap = ValuationSnapshot(forward_pe=9, ev_to_ebitda=7)
    expensive = ValuationSnapshot(forward_pe=45, ev_to_ebitda=28)
    assert score_valuation(cheap).score > 80
    assert score_valuation(expensive).score < 20


def test_valuation_skips_negative_multiples_and_penalizes_losses():
    negative = ValuationSnapshot(trailing_pe=-30, peg_ratio=-2)
    assert score_valuation(negative).score == 50.0  # nothing meaningful to score

    snapshot = ValuationSnapshot(trailing_pe=15, forward_pe=14)
    assert score_valuation(snapshot, loss_making=True).score < score_valuation(snapshot).score


def test_negative_equity_scores_worst_on_leverage():
    healthy = [make_quarter(f"Q{i}", 100, total_debt=30, total_equity=100) for i in range(4)]
    negative = [make_quarter(f"Q{i}", 100, total_debt=30, total_equity=-100) for i in range(4)]
    healthy_score = score_debt(compute_quarter_metrics(healthy)).score
    negative_result = score_debt(compute_quarter_metrics(negative))
    assert negative_result.score < healthy_score
    assert negative_result.metrics["latest_debt_to_equity"] < 0


def test_interest_coverage_and_leverage_move_debt_score():
    safe = [make_quarter(f"Q{i}", 100, operating_income=40, interest_expense=1, ebitda=50, total_debt=40) for i in range(4)]
    stretched = [make_quarter(f"Q{i}", 100, operating_income=3, interest_expense=2, ebitda=5, total_debt=40) for i in range(4)]
    assert score_debt(compute_quarter_metrics(safe)).score > score_debt(compute_quarter_metrics(stretched)).score
