import pytest

from stock_evolution_model import StockEvolutionModel, format_report
from stock_evolution_model.cli import main
from stock_evolution_model.demo_data import generate_demo_fundamentals
from stock_evolution_model.fetch import _build_reported
from stock_evolution_model.types import ReportedMetrics


def _category(report, name):
    return next(c for c in report.categories if c.name == name)


def _snapshot(**reported):
    snapshot = generate_demo_fundamentals("MSFT")
    snapshot.reported = ReportedMetrics(**reported)
    return snapshot


def test_build_reported_converts_units_and_rejects_junk():
    reported = _build_reported(
        {
            "revenueGrowth": 0.083,
            "profitMargins": 0.25,
            "returnOnEquity": 1.47,
            "debtToEquity": 145.3,  # percent -> 1.453x
            "currentRatio": 0.87,
            "freeCashflow": 90.0,
            "totalRevenue": 400.0,
        }
    )
    assert reported.revenue_growth == 0.083
    assert reported.debt_to_equity == pytest.approx(1.453)
    assert reported.fcf_margin == pytest.approx(0.225)

    junk = _build_reported(
        {"revenueGrowth": float("nan"), "profitMargins": None, "returnOnEquity": "n/a",
         "debtToEquity": True, "freeCashflow": 5.0, "totalRevenue": 0}
    )
    assert junk == ReportedMetrics()


def test_reported_figures_override_own_calculation():
    report = StockEvolutionModel().analyze_snapshot(
        _snapshot(revenue_growth=0.0821, net_margin=0.31, roe=0.44, fcf_margin=0.27)
    )
    growth = _category(report, "Revenue Growth")
    assert growth.metrics["latest_growth_pct"] == pytest.approx(8.21)
    assert growth.metrics["growth_basis"].startswith("Yahoo reported")

    profitability = _category(report, "Profitability")
    assert profitability.metrics["latest_net_margin_pct"] == pytest.approx(31.0)
    assert profitability.metrics["latest_roe_pct"] == pytest.approx(44.0)
    assert profitability.metrics["basis"] == "Yahoo reported (trailing 12 months)"

    assert _category(report, "Cash Flow Trends").metrics["latest_fcf_margin_pct"] == pytest.approx(27.0)


def test_falls_back_to_own_calculation_when_nothing_reported():
    report = StockEvolutionModel().analyze_snapshot(_snapshot())
    assert not _category(report, "Revenue Growth").metrics["growth_basis"].startswith("Yahoo")
    assert _category(report, "Profitability").metrics["basis"] == "trailing 12 months"
    assert _category(report, "Debt Levels").metrics["basis"] == "computed from statements"
    assert {c.used for c in report.comparisons} == {"computed"}


def test_partial_reported_figures_mix_sources():
    report = StockEvolutionModel().analyze_snapshot(_snapshot(net_margin=0.20))
    profitability = _category(report, "Profitability")
    assert profitability.metrics["latest_net_margin_pct"] == pytest.approx(20.0)
    assert profitability.metrics["basis"].startswith("Yahoo reported where available")
    used = {c.metric: c.used for c in report.comparisons}
    assert used["Net margin"] == "reported" and used["ROE"] == "computed"


def test_reported_leverage_drives_debt_score():
    model = StockEvolutionModel()
    calm = _category(model.analyze_snapshot(_snapshot(debt_to_equity=0.2, current_ratio=2.4)), "Debt Levels")
    strained = _category(model.analyze_snapshot(_snapshot(debt_to_equity=6.0, current_ratio=0.5)), "Debt Levels")
    assert calm.score > strained.score
    assert calm.metrics["latest_debt_to_equity"] == 0.2
    assert calm.metrics["basis"] == "Yahoo reported D/E and current ratio"


def test_reported_negative_margin_flags_loss_making():
    model = StockEvolutionModel()
    profitable = _category(model.analyze_snapshot(_snapshot(net_margin=0.10)), "Valuation")
    loss = _category(model.analyze_snapshot(_snapshot(net_margin=-0.10)), "Valuation")
    assert loss.metrics["loss_making"] is True
    assert profitable.metrics["loss_making"] is False
    assert loss.score < profitable.score


def test_comparison_records_difference():
    report = StockEvolutionModel().analyze_snapshot(_snapshot(revenue_growth=0.05))
    growth = next(c for c in report.comparisons if c.metric == "Revenue growth")
    assert growth.reported == 0.05 and growth.used == "reported"
    assert growth.difference == pytest.approx(growth.computed - 0.05)
    assert next(c for c in report.comparisons if c.metric == "ROE").difference is None

    exported = report.to_dict()["source_comparison"]
    assert {row["metric"] for row in exported} == {
        "Revenue growth", "Net margin", "ROE", "FCF margin", "Debt/equity", "Current ratio",
    }


def test_audit_output_is_opt_in_and_lists_both_values():
    snapshot = _snapshot(revenue_growth=0.05, net_margin=0.2)
    snapshot.is_demo_data = False  # pretend it came from Yahoo so the table renders
    report = StockEvolutionModel().analyze_snapshot(snapshot)

    assert "VALUE CHECK" not in format_report(report)
    text = format_report(report, audit=True)
    assert "VALUE CHECK" in text
    assert "Revenue growth" in text and "+5.00%" in text and "pts" in text
    assert "Yahoo" in text and "own calc" in text


def test_audit_on_demo_data_explains_there_is_nothing_to_compare():
    report = StockEvolutionModel().analyze_snapshot(generate_demo_fundamentals("AAPL"))
    assert "no Yahoo figures" in format_report(report, audit=True)


def test_cli_audit_flag(capsys):
    assert main(["AAPL", "--demo", "--audit"]) == 0
    assert "VALUE CHECK" in capsys.readouterr().out
    assert main(["AAPL", "--demo"]) == 0
    assert "VALUE CHECK" not in capsys.readouterr().out


def test_numbers_are_shown_with_two_decimals():
    import re

    snapshot = _snapshot(revenue_growth=0.0821, net_margin=0.3137, roe=0.4412, fcf_margin=0.2705)
    snapshot.is_demo_data = False
    text = format_report(StockEvolutionModel().analyze_snapshot(snapshot), audit=True)

    assert "Growth: +8.21%" in text
    assert "Net margin: +31.37%" in text
    assert "ROE: +44.12%" in text
    assert "FCF margin: +27.05%" in text
    # every computed percentage / multiple carries exactly two decimals
    # (the "how it's scored" lines describe score bands, not computed values)
    values = [
        m
        for line in text.splitlines()
        if "how it's scored" not in line
        for m in re.findall(r"\d+\.\d+(?=%|x\b)", line)
    ]
    assert values and all(len(v.split(".")[1]) == 2 for v in values)


def test_json_values_are_rounded_to_two_decimals():
    snapshot = _snapshot(revenue_growth=0.082134567, debt_to_equity=1.456789)
    data = StockEvolutionModel().analyze_snapshot(snapshot).to_dict()

    rows = {r["metric"]: r for r in data["source_comparison"]}
    assert rows["Revenue growth"]["reported"] == 0.0821  # 8.21%
    assert rows["Debt/equity"]["reported"] == 1.46
    valuation = next(c for c in data["categories"] if c["name"] == "Valuation")["metrics"]
    for value in valuation.values():
        if isinstance(value, float):
            assert value == round(value, 2)
