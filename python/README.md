# AI-Powered Stock Evolution Model

A standalone Python model that evaluates a company's fundamental
trajectory across five categories:

- **Revenue growth** — measured on the most reliable basis available
  (trailing 12 months vs the prior 12, else latest quarter vs the same
  quarter last year, else fiscal year vs prior year, and only as a last
  resort quarter-over-quarter, which is distorted by seasonality). The report
  always states which basis was used.
- **Profitability** — trailing-12-month net margin and annual return on
  equity (ROE)
- **Valuation metrics** — PEG, trailing P/E, forward P/E, EV/EBITDA and
  price/sales. Negative or missing multiples are skipped, and loss-making
  companies get a zero-score component instead of silently looking cheap.
- **Debt levels** — debt/equity, current ratio, interest coverage and
  debt/EBITDA. Negative equity scores worst on leverage.
- **Cash flow trends** — trailing-12-month free cash flow margin and its
  trend across recent quarters

Each category is scored 0-100 with a letter grade (A-F) and a trend
(`Improving` / `Stable` / `Deteriorating`), and combined into a weighted
overall score. Every score traces back to a specific metric and threshold —
this is a transparent multi-factor model, not a black box.

It fetches up to eight quarters (plus fiscal-year statements) via
[`yfinance`](https://github.com/ranaroussi/yfinance), no API key required.

**Live data is the default and there is no silent fallback.** If a ticker's
data can't be fetched (no network, unknown ticker, `yfinance` missing) you get
an explicit error for that ticker and exit code 1. To try the model without
network access, opt in to deterministic synthetic data with `--demo`; those
reports are clearly labeled `[DEMO DATA]` / `is_demo_data`.

## Setup

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m stock_evolution_model AAPL MSFT        # live Yahoo Finance data
python -m stock_evolution_model AAPL --json      # machine-readable
python -m stock_evolution_model AAPL --demo      # synthetic data, no network
```

Tickers are plain command-line arguments, in the form Yahoo Finance uses
(`AAPL`, `BRK-B`, ...). A ticker that fails prints an error to stderr; the
others still run.

Or from code:

```python
from stock_evolution_model import StockEvolutionModel, format_report

model = StockEvolutionModel()
report = model.analyze("AAPL")             # raises DataUnavailableError on failure
print(format_report(report))
print(report.to_dict())

demo = model.analyze("AAPL", demo=True)     # synthetic data, no network
```

Custom category weights (must be positive; they're renormalized to sum to 1):

```python
model = StockEvolutionModel(weights={
    "Revenue Growth": 0.30,
    "Profitability": 0.30,
    "Valuation": 0.10,
    "Debt Levels": 0.15,
    "Cash Flow Trends": 0.15,
})
```

## Tests

```bash
cd python
pytest
```

Tests run entirely offline: they use the synthetic demo-data generator and a
fake `yfinance` ticker, so no network access is required.

## Project structure

```
stock_evolution_model/
  types.py       # dataclasses: raw fundamentals, valuation, scores, report
  demo_data.py   # deterministic per-symbol synthetic fundamentals (--demo only)
  fetch.py       # live fetch via yfinance; raises DataUnavailableError on failure
  metrics.py     # derived ratios, TTM figures, best-basis revenue growth, trend slope
  scoring.py     # 0-100 heuristic scoring per category + letter grades
  model.py       # StockEvolutionModel orchestrator + text report formatting
  cli.py         # `python -m stock_evolution_model TICKER [...]`
```
