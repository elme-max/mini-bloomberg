"use client";

import useSWR from "swr";
import type { InsightsResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const TONE_STYLE: Record<InsightsResponse["outlookTone"], string> = {
  positive: "bg-up/15 text-up border-up/30",
  neutral: "bg-surface-2 text-muted border-border",
  cautious: "bg-down/15 text-down border-down/30",
};

export default function InsightPanel({ symbol }: { symbol: string }) {
  const { data, isLoading, error } = useSWR<InsightsResponse>(
    `/api/insights/${symbol}`,
    fetcher
  );

  return (
    <div className="rounded-lg border border-accent/30 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-medium text-muted">
          <span className="text-accent">✦</span> AI investment insights
        </h2>
        {data && (
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] capitalize ${TONE_STYLE[data.outlookTone]}`}
          >
            {data.outlookTone}
          </span>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted">Analyzing headlines and fundamentals…</p>}
      {error && <p className="text-sm text-down">Could not generate insights right now.</p>}

      {data && (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-foreground">{data.headlineSummary}</p>
          <ul className="space-y-1.5">
            {data.insights.map((point, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-foreground">
                <span className="mt-0.5 text-accent">•</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
          <p className="border-t border-border/60 pt-2 text-[11px] text-muted">
            {data.disclaimer}{" "}
            {data.generatedBy === "heuristic" && (
              <>· Set ANTHROPIC_API_KEY for richer, model-generated summaries.</>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
