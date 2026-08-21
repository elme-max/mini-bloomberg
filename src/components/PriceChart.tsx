"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/format";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const RANGES = ["1mo", "6mo", "1y", "5y"] as const;

export default function PriceChart({
  symbol,
  currency,
}: {
  symbol: string;
  currency?: string;
}) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("6mo");
  const { data, isLoading } = useSWR<{ history: HistoryPoint[] }>(
    `/api/history/${symbol}?range=${range}`,
    fetcher
  );

  const history = data?.history ?? [];
  const first = history[0]?.close;
  const last = history[history.length - 1]?.close;
  const up = first != null && last != null ? last >= first : true;
  const color = up ? "#2fbf71" : "#ef4d5e";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted">Price history</h2>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded px-2 py-1 text-xs font-medium transition ${
                range === r
                  ? "bg-accent text-black"
                  : "text-muted hover:bg-surface-2 hover:text-foreground"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="h-64 w-full">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            Loading chart…
          </div>
        ) : history.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted">
            No price history available.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`grad-${symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#8b95a7" }}
                tickFormatter={(d: string) => formatDate(d)}
                minTickGap={40}
                axisLine={{ stroke: "#232a38" }}
                tickLine={false}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 11, fill: "#8b95a7" }}
                tickFormatter={(v: number) => v.toFixed(0)}
                width={48}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#161c28",
                  border: "1px solid #232a38",
                  borderRadius: 6,
                  fontSize: 12,
                }}
                labelFormatter={(d) => formatDate(String(d))}
                formatter={(value) => [formatCurrency(Number(value), currency), "Close"]}
              />
              <Area
                type="monotone"
                dataKey="close"
                stroke={color}
                strokeWidth={1.5}
                fill={`url(#grad-${symbol})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
