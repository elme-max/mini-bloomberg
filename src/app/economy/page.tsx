import { getEconomicIndicators } from "@/lib/fred";
import EconomicIndicatorCard from "@/components/EconomicIndicatorCard";

export const revalidate = 3600;

export default async function EconomyPage() {
  const indicators = await getEconomicIndicators();
  const usingMock = indicators.some((i) => i.source === "mock");

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <h1 className="text-xl font-semibold text-foreground">Economic indicators</h1>
      <p className="mt-1 text-sm text-muted">
        Headline macro data from the Federal Reserve (FRED).
      </p>
      {usingMock && (
        <p className="mt-2 rounded-md border border-accent/30 bg-accent/10 px-3 py-2 text-xs text-accent">
          Showing demo data for series without a live connection. Set the{" "}
          <code className="font-mono">FRED_API_KEY</code> environment variable (free at
          fred.stlouisfed.org) to pull live data.
        </p>
      )}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {indicators.map((ind) => (
          <EconomicIndicatorCard key={ind.id} indicator={ind} />
        ))}
      </div>
    </div>
  );
}
