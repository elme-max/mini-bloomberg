import type { EarningsData } from "@/lib/types";
import { formatCompact, formatDate, formatNumber } from "@/lib/format";

export default function EarningsPanel({ earnings }: { earnings: EarningsData }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted">Earnings</h2>
        {earnings.nextEarningsDate && (
          <span className="rounded bg-surface-2 px-2 py-1 text-xs text-accent">
            Next report: {formatDate(earnings.nextEarningsDate)}
          </span>
        )}
      </div>

      {(earnings.revenueTTM || earnings.earningsTTM) && (
        <div className="mb-3 grid grid-cols-2 gap-3">
          <div className="rounded-md border border-border/70 bg-surface-2 px-3 py-2">
            <div className="text-[11px] text-muted">Revenue (TTM)</div>
            <div className="font-mono text-sm">{formatCompact(earnings.revenueTTM)}</div>
          </div>
          <div className="rounded-md border border-border/70 bg-surface-2 px-3 py-2">
            <div className="text-[11px] text-muted">Net income (TTM)</div>
            <div className="font-mono text-sm">{formatCompact(earnings.earningsTTM)}</div>
          </div>
        </div>
      )}

      {earnings.history.length === 0 ? (
        <p className="text-sm text-muted">No earnings history available.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-1.5 font-medium">Quarter</th>
              <th className="py-1.5 font-medium text-right">EPS actual</th>
              <th className="py-1.5 font-medium text-right">EPS est.</th>
              <th className="py-1.5 font-medium text-right">Surprise</th>
            </tr>
          </thead>
          <tbody>
            {earnings.history.map((h) => {
              const beat = (h.surprisePercent ?? 0) >= 0;
              return (
                <tr key={h.date} className="border-t border-border/60">
                  <td className="py-1.5 text-muted">{formatDate(h.date)}</td>
                  <td className="py-1.5 text-right font-mono">{formatNumber(h.epsActual)}</td>
                  <td className="py-1.5 text-right font-mono text-muted">
                    {formatNumber(h.epsEstimate)}
                  </td>
                  <td
                    className={`py-1.5 text-right font-mono ${
                      h.surprisePercent == null ? "text-muted" : beat ? "text-up" : "text-down"
                    }`}
                  >
                    {h.surprisePercent == null ? "—" : `${beat ? "+" : ""}${h.surprisePercent.toFixed(1)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
