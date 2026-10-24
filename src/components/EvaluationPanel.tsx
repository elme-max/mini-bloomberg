"use client";

import { Fragment } from "react";
import useSWR from "swr";
import type { EvaluationCategory, EvaluationReport, EvaluationTrend } from "@/lib/types";

async function fetcher(url: string): Promise<EvaluationReport> {
  const res = await fetch(url);
  const body = await res.json();
  if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`);
  return body;
}

function gradeColor(grade: string): { text: string; bar: string } {
  if (grade === "A" || grade === "B") return { text: "text-up", bar: "bg-up" };
  if (grade === "C") return { text: "text-accent", bar: "bg-accent" };
  return { text: "text-down", bar: "bg-down" };
}

const TREND: Record<EvaluationTrend, { icon: string; color: string }> = {
  Improving: { icon: "▲", color: "text-up" },
  Stable: { icon: "–", color: "text-muted" },
  Deteriorating: { icon: "▼", color: "text-down" },
};

// Headline figures shown under each category: [label, metrics key, unit].
const HEADLINES: Record<string, [string, string, "%" | "x" | ""][]> = {
  "Revenue Growth": [["Growth", "latest_growth_pct", "%"]],
  Profitability: [
    ["Net margin", "latest_net_margin_pct", "%"],
    ["ROE", "latest_roe_pct", "%"],
  ],
  Valuation: [
    ["P/E", "trailing_pe", "x"],
    ["Fwd P/E", "forward_pe", "x"],
    ["PEG", "peg_ratio", ""],
    ["EV/EBITDA", "ev_to_ebitda", "x"],
  ],
  "Debt Levels": [
    ["D/E", "latest_debt_to_equity", ""],
    ["Current", "latest_current_ratio", ""],
    ["Int. cover", "latest_interest_coverage", "x"],
  ],
  "Cash Flow Trends": [["FCF margin", "latest_fcf_margin_pct", "%"]],
};

function formatMetric(value: unknown, unit: "%" | "x" | ""): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (unit === "%") return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  return `${value.toFixed(2)}${unit}`;
}

function CategoryRow({ category }: { category: EvaluationCategory }) {
  // A category the sector profile can't judge (e.g. FCF for banks) gets a neutral
  // placeholder score; showing it as a red "D" would read as a verdict.
  const applicable = category.metrics.applicable !== false;
  const color = applicable ? gradeColor(category.grade) : { text: "text-muted", bar: "bg-border" };
  const trend = TREND[category.trend];
  const figures = (HEADLINES[category.name] ?? [])
    .map(([label, key, unit]) => {
      const text = formatMetric(category.metrics[key], unit);
      return text && `${label} ${text}`;
    })
    .filter((figure): figure is string => Boolean(figure));
  const basis = category.metrics.growth_basis;

  return (
    <li title={category.detail}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-foreground">{category.name}</span>
        <span className="flex items-baseline gap-2 font-mono">
          <span className={`text-[11px] ${trend.color}`} title={category.trend}>
            {trend.icon}
          </span>
          {applicable ? (
            <>
              <span className="text-foreground">{Math.round(category.score)}</span>
              <span className={`w-3 text-right font-semibold ${color.text}`}>{category.grade}</span>
            </>
          ) : (
            <span className="text-muted">n/a</span>
          )}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className={`h-full rounded-full ${color.bar}`}
          style={{ width: `${Math.max(2, Math.min(100, category.score))}%` }}
        />
      </div>
      {!applicable && (
        <div className="mt-1 text-[11px] text-muted">Not meaningful for this sector (counted as neutral)</div>
      )}
      {applicable && figures.length > 0 && (
        <div className="mt-1 font-mono text-[11px] text-muted">
          {figures.map((figure, i) => (
            // The separator stays outside the nowrap span so lines can still break between figures.
            <Fragment key={figure}>
              {i > 0 && " · "}
              <span className="whitespace-nowrap">{figure}</span>
            </Fragment>
          ))}
        </div>
      )}
      {typeof basis === "string" && basis !== "n/a" && (
        <div className="text-[11px] text-muted/80">{basis}</div>
      )}
    </li>
  );
}

export default function EvaluationPanel({ symbol, demo }: { symbol: string; demo: boolean }) {
  const { data, isLoading, error } = useSWR<EvaluationReport>(
    `/api/evaluation/${encodeURIComponent(symbol)}${demo ? "?demo=1" : ""}`,
    fetcher,
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted">Fundamentals scorecard</h2>
        {data?.is_demo_data && (
          <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
            demo
          </span>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted">Running the evaluation model…</p>}
      {error && (
        <p className="text-sm text-down">
          Scorecard unavailable. <span className="text-muted">{(error as Error).message}</span>
        </p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex items-end justify-between gap-3">
            <div>
              <div className="text-[11px] text-muted">Overall</div>
              <div className="font-mono text-2xl text-foreground">
                {data.overall_score.toFixed(1)}
                <span className="text-sm text-muted">/100</span>
              </div>
            </div>
            <div className="text-right">
              <div className={`font-mono text-2xl font-semibold ${gradeColor(data.overall_grade).text}`}>
                {data.overall_grade}
              </div>
              <div className={`text-[11px] ${TREND[data.overall_trend].color}`}>
                {TREND[data.overall_trend].icon} {data.overall_trend}
              </div>
            </div>
          </div>

          <ul className="space-y-3">
            {data.categories.map((category) => (
              <CategoryRow key={category.name} category={category} />
            ))}
          </ul>

          <p className="border-t border-border/60 pt-2 text-[11px] leading-relaxed text-muted">
            {data.sector_profile === "Generic"
              ? "Scored on generic thresholds (sector unknown)."
              : `Scored against ${data.sector_profile} thresholds.`}{" "}
            Rule-based score from revenue growth, profitability, valuation, debt and cash flow —
            not a buy/sell recommendation. Hover a row for how it is scored.
            {data.is_demo_data && (
              <> Demo figures come from the model&apos;s own synthetic generator, so they differ from the demo numbers elsewhere on this page.</>
            )}
            {!data.is_demo_data && data.data_notes.length > 0 && <> Data {data.data_notes.join("; ")}.</>}
          </p>
        </div>
      )}
    </div>
  );
}
