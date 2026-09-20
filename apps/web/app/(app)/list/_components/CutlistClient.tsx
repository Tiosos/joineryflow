"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import type { ProjectOut, TrackingItemRow } from "@/lib/pm-types";
import type {
  CutlistDetailOut,
  CutlistHardwareRow,
  CutlistOut,
  CutlistPartRow,
} from "@/lib/cutlist-types";
import { can, type Me } from "@/lib/permissions";

interface Props {
  me: Me;
  projects: ProjectOut[];
  selectedProjectId: number;
  cutlists: CutlistOut[];
  /** Joinery Items in this project holding no cutlist — the link picker's candidates. */
  unlinkedItems: TrackingItemRow[];
  open: CutlistDetailOut | null;
}

/**
 * The Cutlist module workspace (Q474): the `List` tab manages cutlists, the
 * entity Q438 made first-class, rather than mirroring Tracking's item grid.
 *
 * Deep-linkable on `?project_id=&cutlist=` (Q478), which is also what makes the
 * Q545 `target="_blank"` tab land where it should.
 */
export default function CutlistClient({
  me,
  projects,
  selectedProjectId,
  cutlists,
  unlinkedItems,
  open,
}: Props) {
  const router = useRouter();
  const canWrite = can(me, "list", "write");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cutlists;
    return cutlists.filter(
      (c) =>
        String(c.cutlist_no).includes(q) ||
        (c.name ?? "").toLowerCase().includes(q),
    );
  }, [cutlists, query]);

  async function call(path: string, init: RequestInit): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api${path}`, {
        headers: { "content-type": "application/json" },
        ...init,
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        setError(body?.detail?.code ?? body?.detail ?? `Failed (${r.status})`);
        return false;
      }
      router.refresh();
      return true;
    } finally {
      setBusy(false);
    }
  }

  function go(params: Record<string, string | null>) {
    const next = new URLSearchParams({ project_id: String(selectedProjectId) });
    for (const [k, v] of Object.entries(params)) {
      if (v == null) next.delete(k);
      else next.set(k, v);
    }
    router.push(`/list?${next.toString()}`);
  }

  async function createCutlist() {
    // Q442: the number is allocated by the server on creation. The caller
    // never supplies one, so this posts a name at most.
    const name = window.prompt("Name for the new cutlist (optional)");
    if (name === null) return;
    const ok = await call(`/projects/${selectedProjectId}/cutlists`, {
      method: "POST",
      body: JSON.stringify({ name: name.trim() || null }),
    });
    if (ok) router.refresh();
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-h-line bg-h-surface p-3">
        <label className="text-xs font-medium text-h-muted">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => router.push(`/list?project_id=${e.target.value}`)}
          className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm text-h-ink"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code} — {p.name}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Cutlist # or name"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-52 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
        />
        <span className="text-xs text-h-muted">
          {cutlists.length} cutlist{cutlists.length === 1 ? "" : "s"}
        </span>
        {canWrite && (
          <button
            type="button"
            onClick={createCutlist}
            disabled={busy}
            className="ml-auto rounded bg-h-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          >
            + New cutlist
          </button>
        )}
      </div>

      {error && (
        <div role="alert" className="rounded border border-h-line bg-h-bg p-2 text-xs text-[#b4443d]">
          {error}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="overflow-hidden rounded-lg border border-h-line bg-h-surface">
          <table className="w-full text-xs">
            <thead className="bg-h-bg text-h-muted">
              <tr>
                <Th>Cutlist</Th>
                <Th>Name</Th>
                <Th align="right">Items</Th>
                <Th>Created by</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-h-muted">
                    {cutlists.length === 0
                      ? "No cutlists on this project yet."
                      : "No cutlist matches your search."}
                  </td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr
                    key={c.cutlist_id}
                    onClick={() => go({ cutlist: String(c.cutlist_id) })}
                    className={`cursor-pointer border-t border-h-line hover:bg-h-bg ${
                      open?.cutlist_id === c.cutlist_id ? "bg-h-bg" : ""
                    }`}
                  >
                    <td className="px-2 py-1.5 font-mono text-h-ink">{c.cutlist_no}</td>
                    <td className="px-2 py-1.5 text-h-ink">{c.name ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-h-ink">
                      {c.item_count}
                    </td>
                    <td className="px-2 py-1.5 text-h-muted">{c.created_by_name ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {open ? (
          <CutlistDetail
            cutlist={open}
            canWrite={canWrite}
            busy={busy}
            unlinkedItems={unlinkedItems}
            onClose={() => go({ cutlist: null })}
            call={call}
          />
        ) : (
          <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-sm text-h-muted">
            Select a cutlist to see the items on it.
          </div>
        )}
      </div>
    </div>
  );
}

function CutlistDetail({
  cutlist,
  canWrite,
  busy,
  unlinkedItems,
  onClose,
  call,
}: {
  cutlist: CutlistDetailOut;
  canWrite: boolean;
  busy: boolean;
  unlinkedItems: TrackingItemRow[];
  onClose: () => void;
  call: (path: string, init: RequestInit) => Promise<boolean>;
}) {
  const [linkId, setLinkId] = useState("");
  // §1218 asks for the parts and hardware themselves. Three panes rather than
  // one long page: the same cutlist is read as "who is on it", "what to cut"
  // and "what to buy" by different people.
  const [pane, setPane] = useState<"items" | "parts" | "hardware">("items");

  async function rename() {
    const name = window.prompt("Cutlist name", cutlist.name ?? "");
    if (name === null) return;
    await call(`/cutlists/${cutlist.cutlist_id}`, {
      method: "PATCH",
      body: JSON.stringify({ name: name.trim() || null }),
    });
  }

  async function remove() {
    // The API refuses this while items are linked (HAS_ITEMS), so the
    // confirmation is about intent, not about cascading anything away.
    if (!window.confirm(`Delete cutlist ${cutlist.cutlist_no}?`)) return;
    if (await call(`/cutlists/${cutlist.cutlist_id}`, { method: "DELETE" })) {
      onClose();
    }
  }

  return (
    <div className="rounded-lg border border-h-line bg-h-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-h-line p-3">
        <span className="font-mono text-lg text-h-ink">{cutlist.cutlist_no}</span>
        <span className="text-sm text-h-ink">{cutlist.name ?? "Unnamed"}</span>
        <span className="text-xs text-h-muted">
          {cutlist.item_count} item{cutlist.item_count === 1 ? "" : "s"}
        </span>
        <div className="ml-auto flex gap-2">
          {canWrite && (
            <>
              <button
                type="button"
                onClick={rename}
                disabled={busy}
                className="rounded border border-h-line px-2 py-1 text-xs text-h-ink disabled:opacity-50"
              >
                Rename
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={busy}
                className="rounded border border-h-line px-2 py-1 text-xs text-[#b4443d] disabled:opacity-50"
              >
                Delete
              </button>
            </>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line px-2 py-1 text-xs text-h-muted"
          >
            Close
          </button>
        </div>
      </div>

      {canWrite && (
        <div className="flex flex-wrap items-center gap-2 border-b border-h-line p-3">
          <select
            value={linkId}
            onChange={(e) => setLinkId(e.target.value)}
            className="min-w-[220px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
          >
            <option value="">Add an item without a cutlist…</option>
            {unlinkedItems.map((i) => (
              <option key={i.id} value={i.id}>
                {i.item_number} · {i.code ?? "—"} · {i.description ?? "—"}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || linkId === ""}
            onClick={async () => {
              if (
                await call(`/cutlists/${cutlist.cutlist_id}/items`, {
                  method: "POST",
                  body: JSON.stringify({ item_id: Number(linkId) }),
                })
              ) {
                setLinkId("");
              }
            }}
            className="rounded bg-h-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            Link
          </button>
        </div>
      )}

      <div className="flex gap-1 border-b border-h-line px-3 py-2">
        {([
          ["items", `Items (${cutlist.items.length})`],
          ["parts", `Parts (${cutlist.parts.length})`],
          ["hardware", `Hardware (${cutlist.hardware.length})`],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setPane(key)}
            className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
              pane === key ? "bg-h-accent text-white" : "text-h-muted hover:text-h-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {pane === "parts" ? (
        <PartsPane parts={cutlist.parts} />
      ) : pane === "hardware" ? (
        <HardwarePane hardware={cutlist.hardware} />
      ) : (
      <table className="w-full text-xs">
        <thead className="bg-h-bg text-h-muted">
          <tr>
            <Th>Item ID</Th>
            <Th>Code</Th>
            <Th>Description</Th>
            <Th>Room</Th>
            <Th>Status</Th>
            {canWrite && <Th />}
          </tr>
        </thead>
        <tbody>
          {cutlist.items.length === 0 ? (
            <tr>
              <td colSpan={canWrite ? 6 : 5} className="px-4 py-8 text-center text-h-muted">
                No items on this cutlist yet.
              </td>
            </tr>
          ) : (
            cutlist.items.map((i) => (
              <tr key={i.item_id} className="border-t border-h-line hover:bg-h-bg">
                <td className="px-2 py-1.5 font-mono text-h-ink">
                  <Link
                    href={`/items/${i.item_id}`}
                    className="hover:text-h-accent hover:underline"
                  >
                    {i.item_number ?? i.item_id}
                  </Link>
                </td>
                <td className="px-2 py-1.5 font-mono text-h-ink">{i.code ?? "—"}</td>
                <td className="px-2 py-1.5 text-h-ink">{i.description ?? "—"}</td>
                <td className="px-2 py-1.5 text-h-muted">
                  {[i.room_no, i.room_desc].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="px-2 py-1.5 text-h-muted">{i.status ?? "—"}</td>
                {canWrite && (
                  <td className="px-2 py-1.5 text-right">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        call(`/cutlists/${cutlist.cutlist_id}/items/${i.item_id}`, {
                          method: "DELETE",
                        })
                      }
                      className="rounded border border-h-line px-2 py-0.5 text-[10px] text-h-muted hover:text-h-ink disabled:opacity-50"
                    >
                      Unlink
                    </button>
                  </td>
                )}
              </tr>
            ))
          )}
        </tbody>
      </table>
      )}
    </div>
  );
}

function PartsPane({ parts }: { parts: CutlistPartRow[] }) {
  if (parts.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-xs text-h-muted">
        No parts on this cutlist yet — its items have no modules.
      </p>
    );
  }
  return (
    <table className="w-full text-xs">
      <thead className="bg-h-bg text-h-muted">
        <tr>
          <Th>Item</Th>
          <Th>Module</Th>
          <Th>Part</Th>
          <Th align="right">Qty</Th>
          <Th align="right">L×W</Th>
          <Th>Board</Th>
          <Th>Edge</Th>
          <Th>Finish</Th>
        </tr>
      </thead>
      <tbody>
        {parts.map((p) => (
          <tr key={p.part_id} className="border-t border-h-line hover:bg-h-bg">
            <td className="px-2 py-1.5 font-mono text-h-muted">{p.item_number ?? p.item_id}</td>
            <td className="px-2 py-1.5 text-h-muted">{p.module_name ?? "—"}</td>
            <td className="px-2 py-1.5 text-h-ink">{p.part_name ?? "—"}</td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-h-ink">
              {p.qty ?? "—"}
            </td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-h-ink">
              {p.len_mm != null && p.wid_mm != null ? `${p.len_mm}×${p.wid_mm}` : "—"}
            </td>
            <td className="px-2 py-1.5 text-h-muted">{p.board_material ?? "—"}</td>
            <td className="px-2 py-1.5 text-h-muted">{p.edge ?? "—"}</td>
            <td className="px-2 py-1.5 text-h-muted">
              {/* §1218's "design instructions": the paint instruction, plus any
                  free-text comment the drafter or the CV import left on the part. */}
              {[p.paint_instruction && p.paint_instruction !== "NONE" ? p.paint_instruction : null,
                p.colour,
                p.comment]
                .filter(Boolean)
                .join(" · ") || "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HardwarePane({ hardware }: { hardware: CutlistHardwareRow[] }) {
  if (hardware.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-xs text-h-muted">
        No hardware lines on this cutlist yet.
      </p>
    );
  }
  return (
    <table className="w-full text-xs">
      <thead className="bg-h-bg text-h-muted">
        <tr>
          <Th>Item</Th>
          <Th>Material</Th>
          <Th>Type</Th>
          <Th>Supplier</Th>
          <Th align="right">Qty</Th>
          <Th>Note</Th>
        </tr>
      </thead>
      <tbody>
        {hardware.map((h) => (
          <tr key={h.line_id} className="border-t border-h-line hover:bg-h-bg">
            <td className="px-2 py-1.5 font-mono text-h-muted">{h.item_number ?? h.item_id}</td>
            <td className="px-2 py-1.5 text-h-ink">{h.catalog_description ?? "—"}</td>
            <td className="px-2 py-1.5 text-h-muted">{h.catalog_source_table ?? "—"}</td>
            <td className="px-2 py-1.5 text-h-muted">{h.catalog_supplier ?? "—"}</td>
            <td className="px-2 py-1.5 text-right font-mono tabular-nums text-h-ink">
              {h.qty ?? "—"}
            </td>
            <td className="px-2 py-1.5 text-h-muted">{h.note ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Th({
  children,
  align = "left",
}: {
  children?: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`px-2 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}
