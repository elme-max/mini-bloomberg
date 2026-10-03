import pytest

from stock_evolution_model import StockEvolutionModel, format_report
from stock_evolution_model.demo_data import generate_demo_fundamentals
from stock_evolution_model.fetch import DataUnavailableError


def test_analyze_snapshot_produces_full_report():
    model = StockEvolutionModel()
    snapshot = generate_demo_fundamentals("AAPL")
    report = model.analyze_snapshot(snapshot)

    assert report.symbol == "AAPL"
    assert report.is_demo_data is True
    assert len(report.categories) == 5
    assert {c.name for c in report.categories} == {
        "Revenue Growth",
        "Profitability",
        "Valuation",
        "Debt Levels",
        "Cash Flow Trends",
    }
    assert 0 <= report.overall_score <= 100
    assert report.overall_grade in ("A", "B", "C", "D", "F")
    assert report.overall_trend in ("Improving", "Stable", "Deteriorating")


def test_analyze_raises_when_live_data_unavailable(monkeypatch):
    import stock_evolution_model.fetch as fetch_module

    monkeypatch.setattr(fetch_module, "yf", None)  # simulate yfinance not installed

    with pytest.raises(DataUnavailableError):
        StockEvolutionModel().analyze("TSLA")


def test_analyze_demo_mode_never_touches_network(monkeypatch):
    import stock_evolution_model.fetch as fetch_module

    monkeypatch.setattr(fetch_module, "yf", None)

    report = StockEvolutionModel().analyze("TSLA", demo=True)
    assert report.is_demo_data is True
    assert report.symbol == "TSLA"


def test_demo_data_is_deterministic():
    a = generate_demo_fundamentals("NVDA")
    b = generate_demo_fundamentals("NVDA")
    assert [q.revenue for q in a.quarters] == [q.revenue for q in b.quarters]


def test_weights_are_normalized():
    model = StockEvolutionModel(weights={"Revenue Growth": 2, "Profitability": 2})
    assert pytest.approx(sum(model.weights.values())) == 1.0


def test_zero_weights_raise():
    with pytest.raises(ValueError):
        StockEvolutionModel(weights={"Revenue Growth": 0})


def test_format_report_contains_key_sections():
    model = StockEvolutionModel()
    snapshot = generate_demo_fundamentals("MSFT")
    report = model.analyze_snapshot(snapshot)
    text = format_report(report)
    assert "MSFT" in text
    assert "OVERALL SCORE:" in text
    assert "Revenue Growth" in text
    assert "[DEMO DATA" in text
