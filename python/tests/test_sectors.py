import pytest

from stock_evolution_model import StockEvolutionModel, format_report
from stock_evolution_model.demo_data import generate_demo_fundamentals
from stock_evolution_model.metrics import compute_quarter_metrics, compute_ttm
from stock_evolution_model.scoring import (
    score_cash_flow,
    score_debt,
    score_profitability,
    score_revenue_growth,
    score_valuation,
)
from stock_evolution_model.sectors import GENERIC, available_sectors, profile_for
from stock_evolution_model.types import ValuationSnapshot

from .test_scoring import make_quarter


def test_profile_lookup_handles_case_aliases_and_unknowns():
    assert profile_for("Technology").name == "Technology"
    assert profile_for("  technology ").name == "Technology"
    assert profile_for("Financials").name == "Financial Services"  # GICS alias
    assert profile_for("Health Care").name == "Healthcare"
    assert profile_for("Consumer Staples").name == "Consumer Defensive"
    assert profile_for("Something Unheard Of") is GENERIC
    assert profile_for(None) is GENERIC
    assert profile_for("") is GENERIC


def test_every_yahoo_sector_has_a_profile():
    yahoo_sectors = {
        "Technology", "Communication Services", "Healthcare", "Financial Services",
        "Consumer Cyclical", "Consumer Defensive", "Industrials", "Energy",
        "Utilities", "Real Estate", "Basic Materials",
    }
    assert yahoo_sectors == set(available_sectors())


def test_bands_are_well_formed():
    for name in available_sectors():
        profile = profile_for(name)
        for field_name in (
            "growth", "net_margin", "roe", "peg", "trailing_pe", "forward_pe", "ev_to_ebitda",
            "price_to_sales", "price_to_book", "debt_to_equity", "current_ratio",
            "interest_coverage", "debt_to_ebitda", "fcf_margin",
        ):
            band = getattr(profile, field_name)
            if band is not None:
                assert len(band) == 2 and band[0] != band[1], (name, field_name)


def test_generic_profile_matches_original_thresholds():
    # Unknown sector must behave exactly as the sector-agnostic model always did.
    quarters = [make_quarter(f"Q{i}", 100 * (1.03**i)) for i in range(6)]
    metrics = compute_quarter_metrics(quarters)
    ttm = compute_ttm(quarters)
    assert score_profitability(metrics, ttm).score == score_profitability(metrics, ttm, GENERIC).score
    assert GENERIC.growth == (-0.20, 0.30)
    assert GENERIC.trailing_pe == (60.0, 8.0)
    assert GENERIC.debt_to_equity == (3.0, 0.0)


def test_same_leverage_is_judged_by_sector():
    # Debt/equity of 4 is alarming for a generic company, normal for a utility.
    quarters = [make_quarter(f"Q{i}", 100, total_debt=400, total_equity=100) for i in range(4)]
    metrics = compute_quarter_metrics(quarters)
    generic = score_debt(metrics, GENERIC)
    utility = score_debt(metrics, profile_for("Utilities"))
    assert utility.score > generic.score
    assert generic.metrics["latest_debt_to_equity"] == 4.0


def test_same_margin_is_judged_by_sector():
    # An 8% net margin is thin for software but healthy for a retailer/utility.
    quarters = [make_quarter(f"Q{i}", 100, net_income=8, total_equity=100) for i in range(4)]
    metrics, ttm = compute_quarter_metrics(quarters), compute_ttm(quarters)
    tech = score_profitability(metrics, ttm, profile_for("Technology"))
    defensive = score_profitability(metrics, ttm, profile_for("Consumer Defensive"))
    assert defensive.score > tech.score


def test_same_growth_and_pe_are_judged_by_sector():
    quarters = [make_quarter(f"Q{i}", 100 * (1.02**i)) for i in range(8)]
    metrics = compute_quarter_metrics(quarters)
    # ~9% growth: strong for utilities (band tops out at 10%), middling for tech (up to 40%).
    utilities = score_revenue_growth(metrics, 0.09, "test", profile_for("Utilities"))
    tech = score_revenue_growth(metrics, 0.09, "test", profile_for("Technology"))
    assert utilities.score > tech.score

    # A P/E of 35 is rich for a utility, ordinary for tech.
    valuation = ValuationSnapshot(trailing_pe=35)
    assert score_valuation(valuation, profile=profile_for("Technology")).score > score_valuation(
        valuation, profile=profile_for("Utilities")
    ).score


def test_financials_skip_irrelevant_debt_inputs():
    bank = profile_for("Financial Services")
    base = dict(total_debt=100, total_equity=100)
    healthy = [make_quarter(f"Q{i}", 100, **base) for i in range(4)]
    # Wreck the inputs that don't apply to banks: current ratio, coverage, EBITDA.
    wrecked = [
        make_quarter(
            f"Q{i}", 100, current_assets=1, current_liabilities=100,
            operating_income=-10, interest_expense=50, ebitda=-10, **base,
        )
        for i in range(4)
    ]
    healthy_result = score_debt(compute_quarter_metrics(healthy), bank)
    wrecked_result = score_debt(compute_quarter_metrics(wrecked), bank)
    assert healthy_result.score == pytest.approx(wrecked_result.score)
    assert wrecked_result.metrics["latest_current_ratio"] is None
    assert wrecked_result.metrics["latest_interest_coverage"] is None
    # ...but a generic profile does punish them.
    assert score_debt(compute_quarter_metrics(wrecked), GENERIC).score < healthy_result.score


def test_financials_cash_flow_is_neutral():
    quarters = [make_quarter(f"Q{i}", 100, operating_cash_flow=60 + i) for i in range(4)]
    metrics, ttm = compute_quarter_metrics(quarters), compute_ttm(quarters)
    result = score_cash_flow(metrics, ttm, profile_for("Financial Services"))
    assert result.score == 50.0
    assert result.trend == "Stable"
    assert score_cash_flow(metrics, ttm, GENERIC).score != 50.0


def test_financials_use_price_to_book_and_skip_ev_ebitda():
    bank = profile_for("Financial Services")
    cheap_book = ValuationSnapshot(price_to_book=0.9)
    pricey_book = ValuationSnapshot(price_to_book=2.8)
    assert score_valuation(cheap_book, profile=bank).score > score_valuation(pricey_book, profile=bank).score
    # EV/EBITDA is ignored for banks entirely...
    assert score_valuation(ValuationSnapshot(ev_to_ebitda=500), profile=bank).score == 50.0
    # ...and P/B is ignored where the profile doesn't use it.
    assert score_valuation(ValuationSnapshot(price_to_book=0.9), profile=GENERIC).score == 50.0


def test_real_estate_skips_peg():
    reit = profile_for("Real Estate")
    assert score_valuation(ValuationSnapshot(peg_ratio=0.6), profile=reit).score == 50.0


def test_report_records_sector_and_profile():
    model = StockEvolutionModel()

    jpm = model.analyze_snapshot(generate_demo_fundamentals("JPM"))
    assert (jpm.sector, jpm.sector_profile) == ("Financial Services", "Financial Services")
    assert jpm.to_dict()["sector_profile"] == "Financial Services"
    assert "Financial Services thresholds" in format_report(jpm)

    unknown = model.analyze_snapshot(generate_demo_fundamentals("ZZZQ"))
    assert unknown.sector is None and unknown.sector_profile == "Generic"
    assert "not sector-adjusted" in format_report(unknown)


def test_sector_changes_the_overall_score():
    model = StockEvolutionModel()
    snapshot = generate_demo_fundamentals("AAPL")
    as_tech = model.analyze_snapshot(snapshot)
    snapshot.sector = None
    as_generic = model.analyze_snapshot(snapshot)
    assert as_tech.sector_profile == "Technology"
    assert as_generic.sector_profile == "Generic"
    assert as_tech.overall_score != as_generic.overall_score


def test_unrecognised_sector_names_the_gap_in_the_report():
    model = StockEvolutionModel()
    snapshot = generate_demo_fundamentals("AAPL")
    snapshot.sector = "Quantum Basket Weaving"
    report = model.analyze_snapshot(snapshot)
    assert report.sector_profile == "Generic"
    assert "no sector profile yet" in format_report(report)
