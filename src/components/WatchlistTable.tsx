import Link from "next/link";
import type { QuoteData } from "@/lib/types";
import { formatCompact, formatCurrency } from "@/lib/format";

export default function WatchlistTable({ quotes }: { quotes: QuoteData[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-4 py-3 font-medium">Symbol</th>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium text-right">Price</th>
            <th className="px-4 py-3 font-medium text-right">Change</th>
            <th className="px-4 py-3 font-medium text-right hidden sm:table-cell">Mkt Cap</th>
          </tr>
        </thead>
        <tbody>
          {quotes.map((q) => {
            const up = q.regularMarketChangePercent >= 0;
            return (
              <tr
                key={q.symbol}
                className="border-b border-border/60 last:border-0 hover:bg-surface-2"
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/stock/${q.symbol}`}
                    className="font-mono font-semibold text-foreground hover:text-accent"
                  >
                    {q.symbol}
                  </Link>
                  {q.source === "demo" && (
                    <span className="ml-2 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">
                      demo
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted truncate max-w-[160px]">{q.shortName}</td>
                <td className="px-4 py-3 text-right font-mono">
                  {formatCurrency(q.regularMarketPrice, q.currency)}
                </td>
                <td
                  className={`px-4 py-3 text-right font-mono ${up ? "text-up" : "text-down"}`}
                >
                  {up ? "▲" : "▼"} {Math.abs(q.regularMarketChangePercent).toFixed(2)}%
                </td>
                <td className="px-4 py-3 text-right font-mono text-muted hidden sm:table-cell">
                  {formatCompact(q.marketCap)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
