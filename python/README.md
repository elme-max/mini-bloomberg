# AI-Powered Stock Evolution Model

A standalone Python model that evaluates a company's fundamental
trajectory across five categories:

- **Revenue growth** — latest YoY (or QoQ) growth rate and its trend
- **Profitability** — net margin and return on equity (ROE)
- **Valuation metrics** — PEG ratio, trailing P/E, price/sales, price/book,
  EV/EBITDA
- **Debt levels** — debt/equity and current ratio
- **Cash flow trends** — free cash flow margin and its trend across recent
  quarters

Each category is scored 0-100 with a letter grade (A-F) and a trend
(`Improving` / `Stable` / `Deteriorating`), and combined into a weighted
overall score. Every score traces back to a specific metric and threshold —
this is a transparent multi-factor model, not a black box.

It fetches up to eight quarters of financial statements via
[`yfinance`](https://github.com/ranaroussi/yfinance) (no API key required).
If `yfinance` isn't installed, the network is unreachable, or a ticker's
statements can't be found, it transparently falls back to deterministic,
per-symbol synthetic data (clearly labeled `is_demo_data`) — the same
fallback pattern the Next.js app in this repo uses for Yahoo Finance.

## Setup

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m stock_evolution_model AAPL MSFT
python -m stock_evolution_model AAPL --json
```

Or from code:

```python
from stock_evolution_model import StockEvolutionModel, format_report

model = StockEvolutionModel()
report = model.analyze("AAPL")
print(format_report(report))
print(report.to_dict())
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

Tests run entirely offline against the synthetic demo-data generator, so
no network access or `yfinance` install is required.

## Project structure

```
stock_evolution_model/
  types.py       # dataclasses: raw fundamentals, valuation, scores, report
  demo_data.py   # deterministic per-symbol synthetic fundamentals (fallback)
  fetch.py       # live fetch via yfinance, falls back to demo_data on failure
  metrics.py     # derived ratios (margins, ROE, D/E, FCF, growth) + trend slope
  scoring.py     # 0-100 heuristic scoring per category + letter grades
  model.py       # StockEvolutionModel orchestrator + text report formatting
  cli.py         # `python -m stock_evolution_model TICKER [...]`
```
