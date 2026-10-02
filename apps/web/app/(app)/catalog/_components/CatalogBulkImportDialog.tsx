"use client";

import { useState } from "react";

import { bulkImport } from "@/lib/catalog-fetch";
import type { BulkImportResp, CatalogSlug } from "@/lib/catalog-types";

interface Props {
  slug: CatalogSlug;
  onClose: () => void;
  onCommitted: (resp: BulkImportResp) => void;
}

function parseCsv(text: string): { headers: string[]; rows: Record<string, string>[] } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",").map((c) => c.trim());
    const r: Record<string, string> = {};
    headers.forEach((h, i) => (r[h] = cells[i] ?? ""));
    return r;
  });
  return { headers, rows };
}

export default function CatalogBulkImportDialog(p: Props) {
  const [csvText, setCsvText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Set after a clean import so the person sees which rows got a supplier link.
  const [result, setResult] = useState<BulkImportResp | null>(null);
  const parsed = parseCsv(csvText);

  const buildRows = (): Record<string, unknown>[] =>
    parsed.rows.map((r) => {
      const out: Record<string, unknown> = { ...r };
      if (out.synonyms != null && typeof out.synonyms === "string") {
        out.synonyms = (out.synonyms as string).split(/\s*\|\s*/).filter(Boolean);
      }
      if (out.default_lead_time_days != null && out.default_lead_time_days !== "") {
        out.default_lead_time_days = Number(out.default_lead_time_days);
      } else {
        delete out.default_lead_time_days;
      }
      if (out.project_id != null && out.project_id !== "") {
        out.project_id = Number(out.project_id);
      }
      return out;
    });

  const onFile = async (f: File | null) => {
    if (!f) return;
    setCsvText(await f.text());
  };

  const onSubmit = async () => {
    setBusy(true); setErr(null);
    try {
      const resp = await bulkImport(p.slug, buildRows());
      if (resp.errors.length > 0) p.onCommitted(resp);
      else setResult(resp);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="fixed inset-0 grid place-items-center bg-black/50">
        <div
          className="max-h-[80vh] w-[640px] overflow-auto rounded-md bg-h-surface p-6 text-h-ink"
          data-testid="bulk-import-result"
        >
          <h2 className="mb-3 text-lg font-semibold">Imported {result.created} rows</h2>
          <p className="text-sm" data-testid="bulk-import-linked">
            {result.linked} linked to a supplier.
          </p>
          {result.unlinked.length > 0 && (
            <div className="mt-3" data-testid="bulk-import-unlinked">
              <p className="text-sm text-h-warn">
                {result.unlinked.length} named a supplier that couldn&apos;t be matched, so{" "}
                {result.unlinked.length === 1 ? "it was" : "they were"} left unlinked — link{" "}
                {result.unlinked.length === 1 ? "it" : "them"} in the grid:
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs text-h-muted">
                {result.unlinked.map((u) => (
                  <li key={u.row_index}>
                    Row {u.row_index + 1} &ldquo;{u.default_supplier}&rdquo; — {u.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-4 flex justify-end">
            <button
              onClick={() => p.onCommitted(result)}
              className="rounded bg-h-accent px-3 py-1 text-sm text-white"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/50">
      <div className="max-h-[80vh] w-[640px] overflow-auto rounded-md bg-h-surface p-6 text-h-ink">
        <h2 className="mb-3 text-lg font-semibold">Bulk import — {p.slug}</h2>
        <p className="mb-2 text-xs text-h-muted">
          A <code>default_supplier</code> that matches a supplier&apos;s name exactly (any case)
          links the row to that supplier; anything else is listed afterwards and left unlinked.
        </p>
        <input type="file" accept=".csv,text/csv"
               onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
        <textarea
          className="mt-2 h-32 w-full border border-h-line p-2 font-mono text-xs"
          placeholder={"header1,header2,...\nval,val,..."}
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
        />
        {parsed.headers.length > 0 && (
          <div className="mt-2 text-xs text-h-muted">
            Detected {parsed.rows.length} rows · headers: {parsed.headers.join(", ")}
          </div>
        )}
        {err && <div className="mt-2 text-xs text-rose-700">{err}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={p.onClose} className="rounded border border-h-line px-3 py-1 text-sm">
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={busy || parsed.rows.length === 0}
            className="rounded bg-h-accent px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {busy ? "Importing…" : `Import ${parsed.rows.length} rows`}
          </button>
        </div>
      </div>
    </div>
  );
}
