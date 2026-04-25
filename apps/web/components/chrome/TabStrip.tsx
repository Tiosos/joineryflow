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

export function TabStrip() {
  const p = usePathname();
  return (
    <nav className="flex gap-1 border-b border-h-line px-4 bg-h-surface">
      {TABS.map((t) => {
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
      })}
    </nav>
  );
}
