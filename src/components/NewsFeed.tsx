import type { NewsItem } from "@/lib/types";
import { timeAgo } from "@/lib/format";

export default function NewsFeed({ news }: { news: NewsItem[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-medium text-muted">Company news</h2>
      {news.length === 0 ? (
        <p className="text-sm text-muted">No recent headlines found.</p>
      ) : (
        <ul className="divide-y divide-border/60">
          {news.map((n) => (
            <li key={n.uuid} className="py-2.5 first:pt-0 last:pb-0">
              <a
                href={n.link}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-sm text-foreground hover:text-accent"
              >
                {n.title}
              </a>
              <div className="mt-1 text-xs text-muted">
                {n.publisher} · {timeAgo(n.providerPublishTime)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
