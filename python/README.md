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

## Sector-aware scoring

Companies are judged against thresholds for **their own sector** (Yahoo
Finance's `sector` field), so a bank's leverage or a software firm's P/E isn't
held to the same yardstick as an industrial's. Examples of what changes:

- A debt/equity of 4 is alarming for a generic company but normal for a utility.
- An 8% net margin is thin for software but healthy for a food producer.
- **Financial Services** skips metrics that don't apply to banks (current
  ratio, interest coverage, EBITDA multiples, FCF margin) and scores
  price/book instead; **Real Estate** skips PEG and current ratio.
- Unknown or missing sectors fall back to the original generic thresholds, and
  the report says so (`Sector: unknown (generic thresholds, not sector-adjusted)`).

Supported sectors: Technology, Communication Services, Healthcare, Financial
Services, Consumer Cyclical, Consumer Defensive, Industrials, Energy,
Utilities, Real Estate and Basic Materials (GICS-style names like
"Financials" or "Consumer Staples" are accepted too).

> **These bands are hand-picked rules of thumb, not statistically derived from
> peer data.** Each is roughly "weak" and "strong" for a typical company in the
> sector. Treat them as a sensible starting point; they live in
> `stock_evolution_model/sectors.py` and are easy to edit. Tuning them against
> a backtest would be the next step before relying on the scores.

## Data and fallback behavior

It fetches up to eight quarters (plus fiscal-year statements) via
[`yfinance`](https://github.com/ranaroussi/yfinance), no API key required.

**Live data is the default and there is no silent fallback.** If a ticker's
data can't be fetched (no network, unknown ticker, `yfinance` missing) you get
an explicit error for that ticker and exit code 1. To try the model without
network access, opt in to deterministic synthetic data with `--demo`; those
reports are clearly labeled `[DEMO DATA]` / `is_demo_data`.

## Where the numbers come from (and matching Yahoo)

The headline "current" figures - revenue growth (latest quarter vs the same
quarter last year), net margin, ROE, FCF margin, debt/equity and current
ratio - are taken **as Yahoo Finance publishes them** whenever it provides
them, so they match what you see on the Yahoo page. The valuation multiples
(P/E, forward P/E, PEG, EV/EBITDA, P/S) always come straight from Yahoo.

When Yahoo doesn't publish a figure, the model falls back to its own
calculation from the quarterly statements (trailing-12-month sums, annualized
ROE, and so on), and the quarterly trends always come from the statements.
Each category states its basis (`Basis: Yahoo reported (trailing 12 months)`
or `trailing 12 months`).

If a number still looks off, run with `--audit` to print the model's own
calculation side by side with Yahoo's figure for every metric:

```
VALUE CHECK - this model's own calculation vs the figure Yahoo reports
  Metric            Own calc     Yahoo        Diff   Used
  Revenue growth      +18.2%    +12.0%    +6.2 pts   Yahoo
  Debt/equity          0.40x     1.50x       -1.10   Yahoo
```

The same data is in the JSON output under `source_comparison`.

## Backtesting the scores and weights

The category weights (20% each) and the score bands are rules of thumb. The
backtest checks them against what the stocks actually did next: do high scorers
beat low scorers, which categories carry that signal, and would other weights
have done better?

```bash
python -m stock_evolution_model.backtest run --fundamentals fundamentals.csv --prices prices.csv
python -m stock_evolution_model.backtest run ... --horizon 180 --lag 60 --json
python -m stock_evolution_model.backtest export AAPL MSFT --out history   # from Yahoo, see limits below
```

**What it reports**

- **Mean IC** per category and overall: the rank correlation between the score
  and the following return, averaged over dates (above 0 means higher scores
  were followed by higher returns), with a t-stat and the **Top-Bottom** return
  of the best-scored fifth vs the worst-scored fifth.
- **Weight fitting:** weights are fitted on the earliest 60% of dates and judged
  on the later, unseen 40% (never shuffled), pulled halfway back toward equal
  weights. New weights are only recommended if they beat equal weights
  out-of-sample; otherwise the verdict says to keep the defaults.
- **Band diagnostics:** the share of each category's scores stuck at exactly 0
  or 100. A high share means that category's bands are too narrow to separate
  companies. Bands are *diagnosed*, not auto-tuned: fitting dozens of cut-offs
  on limited history would only overfit.

**How look-ahead is avoided:** at each as-of date a company is scored only from
quarters already reported (period end plus `--lag` days, default 45), valuation
multiples are rebuilt from the price on that date, and Yahoo's "current"
figures are never used. The forward-return windows do not overlap
(rebalance spacing = `--horizon`).

**Input files**

`fundamentals.csv` - one row per company per quarter. Required: `symbol`,
`period_end` (YYYY-MM-DD), `revenue`, `gross_profit`, `operating_income`,
`net_income`, `total_assets`, `total_equity`, `total_debt`, `current_assets`,
`current_liabilities`, `interest_expense`, `ebitda`, `operating_cash_flow`,
`capex`. Optional: `shares_outstanding` (enables valuation), `sector`. Blank or
non-numeric required values are an error, never a silent zero.

`prices.csv` - `symbol,date,close` (use split/dividend-adjusted closes).

**Limits you should know about**

- **Yahoo cannot supply enough history.** It serves only ~4-5 recent quarters,
  so `export` is good for trying the pipeline but yields almost no usable
  dates. A meaningful backtest needs years of point-in-time quarterly data
  from a deeper source (aim for 12+ dates and 30+ companies per date; the
  report warns when the sample is smaller).
- **Survivorship bias:** use a universe that includes companies that were
  later delisted or acquired; backtesting only today's survivors flatters
  every score.
- **Reduced valuation factor:** in a backtest, valuation uses trailing P/E, P/S
  and (for financials) P/B from the as-of price. PEG, forward P/E and EV/EBITDA
  need analyst estimates or cash balances that this data does not carry.
- **A passing backtest is evidence, not proof.** Until you run it on real
  multi-year data, the equal default weights remain unvalidated guesses.

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
python -m stock_evolution_model AAPL --audit     # compare own calc vs Yahoo's figures
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
  sectors.py     # per-sector scoring bands (edit these to tune the model)
  scoring.py     # 0-100 heuristic scoring per category + letter grades
  model.py       # StockEvolutionModel orchestrator + text report formatting
  cli.py         # `python -m stock_evolution_model TICKER [...]`
  backtest.py    # point-in-time backtest, weight fitting, Yahoo CSV export
```
