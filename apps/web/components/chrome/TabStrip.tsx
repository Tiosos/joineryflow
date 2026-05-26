"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/tracking", label: "Tracking" },
  { href: "/list", label: "List" },
  { href: "/shop-dwgs", label: "Shop Dwgs" },
  { href: "/isample", label: "iSample" },
  { href: "/orderbook", label: "Orderbook" },
];

const SECONDARY_TABS = [
  { href: "/catalog", label: "Catalog" },
  { href: "/shop-floor", label: "Shop Floor" },
  { href: "/cut-floor", label: "Cut Floor" },
  { href: "/estimating", label: "Estimating" },
  { href: "/customers", label: "Customers" },
];

export function TabStrip() {
  const p = usePathname();
  function renderTab(t: { href: string; label: string }) {
    const active = p === t.href || p.startsWith(`${t.href}/`);
    return (
      <Link
        key={t.href}
        href={t.href}
        className={`px-4 py-2 text-sm transition ${
          active
            ? "border-b-2 border-h-accent text-h-ink font-medium"
            : "text-h-muted hover:text-h-ink"
        }`}
      >
        {t.label}
      </Link>
    );
  }
  return (
    <nav className="flex flex-wrap items-center gap-1 border-b border-h-line px-4 bg-h-surface">
      {TABS.map(renderTab)}
      <span className="mx-2 h-5 w-px bg-h-line" aria-hidden="true" />
      {SECONDARY_TABS.map(renderTab)}
    </nav>
  );
}
