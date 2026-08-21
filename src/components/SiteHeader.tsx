import Link from "next/link";
import TickerSearch from "./TickerSearch";

export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-accent text-sm font-bold text-black">
            m
          </span>
          <span className="font-mono text-sm font-semibold tracking-tight text-foreground">
            mini-bloomberg
          </span>
        </Link>
        <nav className="hidden items-center gap-4 text-sm text-muted sm:flex">
          <Link href="/" className="hover:text-foreground">
            Dashboard
          </Link>
          <Link href="/economy" className="hover:text-foreground">
            Economy
          </Link>
        </nav>
        <div className="ml-auto w-full max-w-sm">
          <TickerSearch />
        </div>
      </div>
    </header>
  );
}
