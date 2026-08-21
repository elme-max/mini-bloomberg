import Link from "next/link";
import { getQuotes } from "@/lib/yahoo";
import { getEconomicIndicators } from "@/lib/fred";
import { DEFAULT_WATCHLIST } from "@/lib/watchlist";
import WatchlistTable from "@/components/WatchlistTable";
import EconomicIndicatorCard from "@/components/EconomicIndicatorCard";

export const revalidate = 60;

export default async function DashboardPage() {
  const [quotes, indicators] = await Promise.all([
    getQuotes([...DEFAULT_WATCHLIST]),
    getEconomicIndicators(),
  ]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Watchlist</h1>
        <p className="mt-1 text-sm text-muted">
          Live prices, ratios, news and AI insights for tracked companies. Search any ticker above.
        </p>
      </div>

      <WatchlistTable quotes={quotes} />

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Economy at a glance</h2>
        <Link href="/economy" className="text-sm text-accent hover:underline">
          View all indicators →
        </Link>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {indicators.slice(0, 3).map((ind) => (
          <EconomicIndicatorCard key={ind.id} indicator={ind} />
        ))}
      </div>
    </div>
  );
}
