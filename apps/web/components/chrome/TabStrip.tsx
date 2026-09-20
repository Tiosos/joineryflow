"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { can, type Me, type Module } from "@/lib/permissions";

interface Tab {
  href: string;
  label: string;
  /** Matrix module gating this tab; `read` is required to see it at all. */
  module: Module;
  /**
   * Q475 + Q545: Tracking, Cutlist (the `List` tab, per Q474) and Orderbook
   * open as their own browser tab, so two of them can sit side by side on two
   * monitors the way the reference system's separate windows did. Q545 chose a
   * plain `target="_blank"` over `window.open` — no popup blockers, no second
   * auth path, and the deep links Q478 preserves still work.
   */
  newTab?: true;
}

const TABS: Tab[] = [
  { href: "/dashboard",  label: "Dashboard", module: "dashboard" },
  { href: "/tracking",   label: "Tracking",  module: "tracking",  newTab: true },
  { href: "/list",       label: "List",      module: "list",      newTab: true },
  { href: "/shop-dwgs",  label: "Shop Dwgs", module: "shop_dwgs" },
  { href: "/isample",    label: "iSample",   module: "isample" },
  { href: "/orderbook",  label: "Orderbook", module: "orderbook", newTab: true },
];

const SECONDARY_TABS: Tab[] = [
  { href: "/catalog",    label: "Catalog",    module: "catalog" },
  { href: "/shop-floor", label: "Shop Floor", module: "shop_floor" },
  { href: "/cut-floor",  label: "Cut Floor",  module: "cut_floor" },
  { href: "/estimating", label: "Estimating", module: "estimating" },
  // /customers is the estimating module's customer registry — same gate.
  { href: "/customers",  label: "Customers",  module: "estimating" },
];

export function TabStrip({ user }: { user: Me }) {
  const p = usePathname();
  function renderTab(t: Tab) {
    const active = p === t.href || p.startsWith(`${t.href}/`);
    return (
      <Link
        key={t.href}
        href={t.href}
        // Already looking at it? Navigate in place rather than cloning the tab
        // you are standing on — Q475 wants two modules side by side, not two
        // copies of one.
        target={t.newTab && !active ? "_blank" : undefined}
        className={`px-4 py-2 text-sm transition ${
          active
            ? "border-b-2 border-h-accent text-h-ink font-medium"
            : "text-h-muted hover:text-h-ink"
        }`}
      >
        {t.label}
        {t.newTab && !active && (
          <span aria-hidden className="ml-1 text-[9px] align-super opacity-60">↗</span>
        )}
      </Link>
    );
  }
  // Fail OPEN, not closed, when the permissions map is entirely absent —
  // e.g. the web tier deployed ahead of an API that predates the field on
  // /auth/me. Blanking the whole nav bar is a worse failure than showing a
  // tab whose API call will 403 anyway (the 403 is the real gate). Once a
  // permissions map is present, a missing module means genuinely no access,
  // so we filter normally.
  const hasPerms = !!user.permissions && Object.keys(user.permissions).length > 0;
  const visible = (t: Tab) => !hasPerms || can(user, t.module, "read");
  const primary = TABS.filter(visible);
  const secondary = SECONDARY_TABS.filter(visible);
  return (
    <nav className="flex flex-wrap items-center gap-1 border-b border-h-line px-4 bg-h-surface">
      {primary.map(renderTab)}
      {primary.length > 0 && secondary.length > 0 && (
        <span className="mx-2 h-5 w-px bg-h-line" aria-hidden="true" />
      )}
      {secondary.map(renderTab)}
    </nav>
  );
}
