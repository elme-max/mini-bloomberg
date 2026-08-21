"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { EconomicIndicator } from "@/lib/types";
import { formatDate } from "@/lib/format";

export default function EconomicIndicatorCard({ indicator }: { indicator: EconomicIndicator }) {
  const up = (indicator.change ?? 0) >= 0;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium text-foreground">{indicator.name}</h3>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-2xl text-foreground">
              {indicator.latestValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
            <span className="text-xs text-muted">{indicator.unit}</span>
          </div>
          <div className="mt-0.5 text-xs text-muted">
            as of {formatDate(indicator.latestDate)}
            {indicator.change != null && (
              <span className={`ml-2 font-mono ${up ? "text-up" : "text-down"}`}>
                {up ? "▲" : "▼"} {Math.abs(indicator.change).toFixed(2)}
              </span>
            )}
          </div>
        </div>
        {indicator.source === "mock" && (
          <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted" title="Set FRED_API_KEY for live data">
            demo data
          </span>
        )}
      </div>
      <div className="mt-2 h-16 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={indicator.series}>
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{
                background: "#161c28",
                border: "1px solid #232a38",
                borderRadius: 6,
                fontSize: 11,
              }}
              labelFormatter={(d) => formatDate(String(d))}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#f5a623"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
