/* Shared topbar chrome for the legacy mockups.
 * Source-of-truth for: 6-tab IA, secondary nav, JTBD-role selector + auth_role mapping.
 * Mirrors apps/web/components/chrome/{TabStrip,SideBar,TopBar}.tsx.
 *
 * Usage in each legacy HTML file:
 *   <div id="h-chrome"></div>
 *   <script src="_chrome.js"></script>
 *   <script>renderChrome('tracking');</script>
 *
 * Valid `active` keys: 'dashboard' | 'tracking' | 'list' | 'shop_dwgs' | 'isample' | 'orderbook'.
 *
 * The legacy file must already declare the .h-topbar / .h-tabs / .h-search / .h-who CSS
 * locally — this script generates HTML only, not styles.
 */

/* JTBD role -> auth_role mapping (CLAUDE.md §"Role model"; mirrors apps/api/app/auth/permissions.py).
 * Drafter is editor with PM-parity grants on orderbook / shop_dwgs / isample / catalog. */
const H_AUTH_ROLE = {
  CEO: "admin",
  PM: "manager",
  DRAFTER: "editor",
  FOREMAN: "editor",
  MACHINE: "editor",
  PROCUREMENT: "purchase_officer",
};

/* Primary 6-tab IA — apps/web/components/chrome/TabStrip.tsx canonical order. */
const TABS = [
  { key: "dashboard", label: "Dashboard", href: "home.html" },
  { key: "tracking",  label: "Tracking",  href: "tracking_dashboard.html" },
  { key: "list",      label: "List",      href: "drafter_item_editor.html" },
  { key: "shop_dwgs", label: "Shop Dwgs", href: "#" },
  { key: "isample",   label: "iSample",   href: "#" },
  { key: "orderbook", label: "Orderbook", href: "procurement_orderbook_dashboard.html" },
];

/* Secondary surfaces — apps/web/components/chrome/SideBar.tsx top section. */
const SECONDARY = [
  { key: "catalog",    label: "Catalog",    title: "Material catalog (#7a)" },
  { key: "cut_floor",  label: "Cut Floor",  title: "CutPlan + CutSchedule (#7c)" },
  { key: "shop_floor", label: "Shop Floor", title: "Shop Floor Ops (#8)" },
];

function hGo(href) {
  if (href && href !== "#") window.location.href = href;
}

function hSetRole(r) {
  try {
    localStorage.setItem("jf-role", r);
  } catch (e) {
    /* ignore */
  }
  hUpdateAuthRoleLabel(r);
}

function hUpdateAuthRoleLabel(r) {
  const lbl = document.getElementById("h-auth-role");
  if (lbl) lbl.textContent = "→ " + (H_AUTH_ROLE[r] || "viewer");
}

function renderChrome(active, opts) {
  opts = opts || {};
  const defaultRole = opts.defaultRole || "DRAFTER";
  const initials = opts.initials || "BM";

  const primaryHTML = TABS.map((t) => {
    const cls = "h-tab" + (t.key === active ? " active" : "");
    const click = t.href === "#" ? "" : ` onclick="hGo('${t.href}')"`;
    return `<div class="${cls}"${click}>${t.label}</div>`;
  }).join("");

  const secondaryHTML = SECONDARY.map(
    (s) => `<div class="h-tab" title="${s.title}">${s.label}</div>`,
  ).join("");

  const host = document.getElementById("h-chrome");
  if (!host) return;
  host.innerHTML = `
    <div class="h-topbar">
      <div class="h-logo">
        <div class="h-logomark">◴</div>
        <div class="h-wordmark">JoineryFlow<sub>Hartwood</sub></div>
      </div>
      <!-- 6-tab IA, canonical order from apps/web/components/chrome/TabStrip.tsx -->
      <div class="h-tabs">${primaryHTML}</div>
      <!-- Secondary surfaces (mirrors apps/web/components/chrome/SideBar.tsx) -->
      <div class="h-tabs" style="border-left:1px solid var(--h-line);padding-left:10px;margin-left:6px;">${secondaryHTML}</div>
      <div class="h-search">
        <span>⌕</span>
        <input placeholder="Jump to project, item, PO…">
        <span class="h-mono" style="font-size:10px;color:var(--h-ink4);">⌘K</span>
      </div>
      <div class="h-who">
        <select id="h-role-select" onchange="hSetRole(this.value)">
          <option value="CEO">CEO</option>
          <option value="PM">PM</option>
          <option value="DRAFTER">Drafter</option>
          <option value="FOREMAN">Foreman</option>
          <option value="MACHINE">Machine</option>
          <option value="PROCUREMENT">Procurement</option>
        </select>
        <span class="h-mono" id="h-auth-role" title="auth_role (apps/api/app/auth/permissions.py)" style="font-size:10px;color:var(--h-ink3);padding:2px 6px;border:1px solid var(--h-line);border-radius:10px;">→ editor</span>
        <div class="h-avatar">${initials}</div>
      </div>
    </div>
  `;

  try {
    const stored = localStorage.getItem("jf-role") || defaultRole;
    const sel = document.getElementById("h-role-select");
    if (sel) sel.value = stored;
    hUpdateAuthRoleLabel(stored);
  } catch (e) {
    /* file:// without storage is fine */
  }
}
