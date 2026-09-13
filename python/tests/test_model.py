import pytest

from stock_evolution_model import StockEvolutionModel, format_report
from stock_evolution_model.demo_data import generate_demo_fundamentals


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


def test_analyze_falls_back_to_demo_data_without_network(monkeypatch):
    # Force the fetch used by the model to return demo data, so this test
    # exercises the fallback path regardless of network/yfinance availability.
    import stock_evolution_model.model as model_module

    def boom(symbol):
        return generate_demo_fundamentals(symbol, reason="forced for test")

    monkeypatch.setattr(model_module, "fetch_fundamentals", boom)

    model = StockEvolutionModel()
    report = model.analyze("TSLA")
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
    assert "Overall:" in text
    assert "Revenue Growth" in text
    assert "[DEMO DATA]" in text
