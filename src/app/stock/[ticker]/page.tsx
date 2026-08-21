import { getEarnings, getNews, getQuote, getRatios } from "@/lib/yahoo";
import { formatCompact, formatCurrency, formatNumber } from "@/lib/format";
import PriceChart from "@/components/PriceChart";
import RatioGrid from "@/components/RatioGrid";
import NewsFeed from "@/components/NewsFeed";
import EarningsPanel from "@/components/EarningsPanel";
import InsightPanel from "@/components/InsightPanel";

export const revalidate = 60;

export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const symbol = ticker.toUpperCase();

  const [quote, ratios, news, earnings] = await Promise.all([
    getQuote(symbol),
    getRatios(symbol),
    getNews(symbol),
    getEarnings(symbol),
  ]);

  const up = quote.regularMarketChangePercent >= 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      {quote.source === "demo" && (
        <p className="mb-4 rounded-md border border-accent/30 bg-accent/10 px-3 py-2 text-xs text-accent">
          Showing demo data — either &ldquo;{symbol}&rdquo; isn&apos;t a recognized ticker, or the
          live Yahoo Finance connection is temporarily unavailable in this environment.
        </p>
      )}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-2">
            <h1 className="font-mono text-2xl font-semibold text-foreground">{quote.symbol}</h1>
            <span className="text-sm text-muted">{quote.longName ?? quote.shortName}</span>
          </div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="font-mono text-3xl text-foreground">
              {formatCurrency(quote.regularMarketPrice, quote.currency)}
            </span>
            <span className={`font-mono text-sm ${up ? "text-up" : "text-down"}`}>
              {up ? "▲" : "▼"} {formatNumber(quote.regularMarketChange)} (
              {Math.abs(quote.regularMarketChangePercent).toFixed(2)}%)
            </span>
          </div>
          <div className="mt-1 text-xs text-muted">
            {quote.exchange} · {quote.marketState}
          </div>
        </div>
        <div className="flex gap-4 text-sm">
          <Stat label="Open" value={formatCurrency(quote.regularMarketOpen, quote.currency)} />
          <Stat
            label="Day range"
            value={`${formatNumber(quote.regularMarketDayLow)} – ${formatNumber(
              quote.regularMarketDayHigh
            )}`}
          />
          <Stat label="Volume" value={formatCompact(quote.regularMarketVolume)} />
          <Stat label="Mkt cap" value={formatCompact(quote.marketCap)} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <PriceChart symbol={symbol} currency={quote.currency} />
          <RatioGrid ratios={ratios} />
          <EarningsPanel earnings={earnings} />
        </div>
        <div className="space-y-4">
          <InsightPanel symbol={symbol} />
          <NewsFeed news={news} />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <div className="text-[11px] text-muted">{label}</div>
      <div className="font-mono text-sm text-foreground">{value}</div>
    </div>
  );
}
