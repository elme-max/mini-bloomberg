import type { RatiosData } from "@/lib/types";
import { formatCompact, formatNumber, formatPercent } from "@/lib/format";

interface RatioDef {
  label: string;
  value: (r: RatiosData) => string;
  hint: string;
}

const RATIO_DEFS: RatioDef[] = [
  {
    label: "P/E (trailing)",
    value: (r) => formatNumber(r.peRatioTrailing),
    hint: "Price ÷ last 12 months earnings per share",
  },
  {
    label: "P/E (forward)",
    value: (r) => formatNumber(r.peRatioForward),
    hint: "Price ÷ analysts' expected earnings",
  },
  {
    label: "PEG ratio",
    value: (r) => formatNumber(r.pegRatio),
    hint: "P/E adjusted for expected growth; near 1 is balanced",
  },
  {
    label: "Price / Book",
    value: (r) => formatNumber(r.priceToBook),
    hint: "Price vs. net asset value per share",
  },
  {
    label: "Price / Sales",
    value: (r) => formatNumber(r.priceToSales),
    hint: "Price vs. revenue per share",
  },
  {
    label: "Dividend yield",
    value: (r) => formatPercent(r.dividendYield, true),
    hint: "Annual dividend as a % of price",
  },
  {
    label: "Profit margin",
    value: (r) => formatPercent(r.profitMargin),
    hint: "Net profit as a % of revenue",
  },
  {
    label: "Operating margin",
    value: (r) => formatPercent(r.operatingMargin),
    hint: "Operating profit as a % of revenue",
  },
  {
    label: "Return on equity",
    value: (r) => formatPercent(r.returnOnEquity),
    hint: "Profit generated per dollar of shareholder equity",
  },
  {
    label: "Return on assets",
    value: (r) => formatPercent(r.returnOnAssets),
    hint: "Profit generated per dollar of assets",
  },
  {
    label: "Debt / Equity",
    value: (r) => formatNumber(r.debtToEquity),
    hint: "Total debt relative to shareholder equity",
  },
  {
    label: "Current ratio",
    value: (r) => formatNumber(r.currentRatio),
    hint: "Short-term assets vs. short-term liabilities",
  },
  {
    label: "Revenue growth",
    value: (r) => formatPercent(r.revenueGrowth),
    hint: "Year-over-year revenue growth",
  },
  {
    label: "Earnings growth",
    value: (r) => formatPercent(r.earningsGrowth),
    hint: "Year-over-year earnings growth",
  },
  {
    label: "Beta",
    value: (r) => formatNumber(r.beta),
    hint: "Volatility vs. the overall market (1 = market average)",
  },
  {
    label: "EPS (TTM)",
    value: (r) => formatNumber(r.eps),
    hint: "Earnings per share, trailing 12 months",
  },
  {
    label: "Free cash flow",
    value: (r) => formatCompact(r.freeCashflow),
    hint: "Cash generated after operating & capital costs",
  },
  {
    label: "52-week range",
    value: (r) =>
      `${formatNumber(r.fiftyTwoWeekLow)} – ${formatNumber(r.fiftyTwoWeekHigh)}`,
    hint: "Lowest and highest closing price in the last year",
  },
];

export default function RatioGrid({ ratios }: { ratios: RatiosData }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium text-muted">Key financial ratios</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {RATIO_DEFS.map((def) => (
          <div
            key={def.label}
            title={def.hint}
            className="rounded-md border border-border/70 bg-surface-2 px-3 py-2"
          >
            <div className="text-[11px] text-muted">{def.label}</div>
            <div className="mt-0.5 font-mono text-sm text-foreground">
              {def.value(ratios)}
            </div>
          </div>
        ))}
      </div>
      {ratios.recommendationKey && (
        <div className="mt-3 text-xs text-muted">
          Analyst consensus:{" "}
          <span className="font-medium text-foreground uppercase">
            {ratios.recommendationKey}
          </span>
          {ratios.targetMeanPrice != null && (
            <> · avg. price target {formatNumber(ratios.targetMeanPrice)}</>
          )}
        </div>
      )}
    </div>
  );
}
