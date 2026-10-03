"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { Me } from "@/lib/session";
import type {
  EstimateDetail,
  EstimateStatus,
  GenerateOrdersResult,
  HardwareMaterialType,
  Line,
  LineHardware,
  LinePart,
  OrderPreview,
  OrderPreviewLine,
  PartMaterialType,
  StageKey,
} from "@/lib/estimating-types";
import { listSupplierOptions } from "@/lib/catalog-fetch";
import type { SupplierOption } from "@/lib/catalog-types";
import { TENDER_STAGE_LABELS, TENDER_STAGE_ORDER } from "@/lib/estimating-types";

function nextStageLabel(status: EstimateStatus | undefined): string | null {
  if (!status) return null;
  const idx = (TENDER_STAGE_ORDER as readonly string[]).indexOf(status);
  if (idx === -1 || idx === TENDER_STAGE_ORDER.length - 1) return null;
  return TENDER_STAGE_LABELS[TENDER_STAGE_ORDER[idx + 1]];
}

interface CatalogRow {
  material_id: number;
  sku: string;
  description: string;
  default_supplier?: string | null;
}

type MaterialKind = PartMaterialType | HardwareMaterialType;

type CatalogMap = Record<MaterialKind, CatalogRow[]>;

const PART_KINDS: PartMaterialType[] = ["BOARD", "CUSTOM", "BENCHTOP"];
const HW_KINDS: HardwareMaterialType[] = ["HARDWARE", "APPLIANCE"];
const ALL_KINDS: MaterialKind[] = [...PART_KINDS, ...HW_KINDS];

const KIND_LABEL: Record<MaterialKind, string> = {
  BOARD: "Board",
  CUSTOM: "Custom",
  BENCHTOP: "Benchtop",
  HARDWARE: "Hardware",
  APPLIANCE: "Appliance",
};

const KIND_SLUG: Record<MaterialKind, string> = {
  BOARD: "board-materials",
  CUSTOM: "custom-made",
  BENCHTOP: "benchtop-materials",
  HARDWARE: "hardware-materials",
  APPLIANCE: "appliances",
};

interface Props {
  me: Me;
  estimate: EstimateDetail;
  catalogs: CatalogMap;
}

const STAGE_KEYS: StageKey[] = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED",
  "PAINTED", "MADE", "DEL", "INST",
];

// The 10 pre-SUBMITTED pipeline stages (Q487/488) share one "in progress"
// look; SUBMITTED and the three terminal outcomes each get their own.
const STATUS_COLOURS: Record<EstimateStatus, string> = {
  OPPORTUNITY: "bg-gray-200 text-gray-700",
  INITIAL_REVIEW: "bg-gray-200 text-gray-700",
  GO_NO_GO: "bg-gray-200 text-gray-700",
  INFO_REQUESTED: "bg-gray-200 text-gray-700",
  DOCS_RECEIVED: "bg-gray-200 text-gray-700",
  ESTIMATING: "bg-gray-200 text-gray-700",
  SUPPLIER_PRICING: "bg-gray-200 text-gray-700",
  INTERNAL_REVIEW: "bg-gray-200 text-gray-700",
  QUOTE_PREPARED: "bg-gray-200 text-gray-700",
  MGMT_APPROVAL: "bg-gray-200 text-gray-700",
  SUBMITTED: "bg-blue-100 text-blue-800",
  WON: "bg-green-100 text-green-800",
  LOST: "bg-red-100 text-red-800",
  WITHDRAWN: "bg-gray-100 text-gray-600",
};

function fmtMoney(s: string | null | undefined): string {
  if (!s) return "$0.00";
  const n = parseFloat(s);
  if (!Number.isFinite(n)) return "$0.00";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function isPartKind(k: MaterialKind): k is PartMaterialType {
  return k === "BOARD" || k === "CUSTOM" || k === "BENCHTOP";
}

function summariseGenerateResult(result: GenerateOrdersResult): string {
  const orderWord = result.orders_created === 1 ? "order" : "orders";
  const lineWord = result.lines_created === 1 ? "line" : "lines";
  let msg = `${result.orders_created} ${orderWord} generated (${result.lines_created} ${lineWord}).`;
  const left = result.uncovered_line_ids?.length ?? 0;
  if (left > 0) {
    const n = result.unassigned.length;
    msg += ` ${left} ${left === 1 ? "line was" : "lines were"} held back whole because ${n}`
      + ` ${n === 1 ? "material on it has" : "materials on them have"} no default supplier`
      + " — link a supplier in the Catalog and generate again.";
  }
  return msg;
}

type CallApiFn = (
  method: string,
  url: string,
  body?: unknown,
) => Promise<{ ok: boolean; data?: unknown; error?: string }>;

interface PickerPayload {
  kind: MaterialKind;
  material_id: number;
  qty: number;
  len_mm?: number | null;
  wid_mm?: number | null;
  paint_instruction: "NONE" | "DOUBLE_SIDE" | "SINGLE_SIDE" | "EDGE_ONLY";
  comment?: string;
}

export default function EstimateDetailClient({ me, estimate: initialEstimate, catalogs }: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const [estimate, setEstimate] = useState(initialEstimate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConvert, setShowConvert] = useState(false);
  const [orderPreview, setOrderPreview] = useState<OrderPreview | null>(null);
  const [generateResult, setGenerateResult] = useState<GenerateOrdersResult | null>(null);

  const currentRev =
    estimate.revisions.find((r) => r.revision_id === estimate.current_revision_id)
    ?? estimate.revisions[0];

  // Lines that became Joinery Items at Convert and no Generate Orders run has
  // covered yet — what "Generate orders" can still order.
  // A line marked "ordered by hand" is not pending either, but is kept in view (below) so
  // the dismissal can be undone.
  const pendingOrderLines = currentRev?.converted_project_id
    ? currentRev.lines.filter(
        (l) => l.included_at_convert && !l.orders_generated_at && !l.orders_dismissed_at,
      ).length
    : 0;
  const dismissedOrderLines = currentRev?.converted_project_id
    ? currentRev.lines.filter((l) => l.included_at_convert && l.orders_dismissed_at).length
    : 0;

  const revParam = sp.get("rev");
  const selectedRevId = revParam ? Number(revParam) : null;
  const selectedRev =
    (selectedRevId && estimate.revisions.find((r) => r.revision_id === selectedRevId))
    || currentRev;
  const isViewingCurrent = selectedRev?.revision_id === currentRev?.revision_id;

  const canWrite =
    me.auth_role === "admin" || me.auth_role === "manager" || me.auth_role === "estimator";
  // "Draft" now means "not yet locked" — any of the 10 pre-SUBMITTED
  // pipeline stages (Q487/488), not a single named status. Matches the
  // backend's own `locked_at IS NULL` gate on line/part/hardware mutations.
  const isDraft = selectedRev?.locked_at == null && isViewingCurrent;

  const refresh = useCallback(async () => {
    const r = await fetch(`/api/estimates/${estimate.estimate_id}`);
    if (r.ok) setEstimate((await r.json()) as EstimateDetail);
  }, [estimate.estimate_id]);

  const callApi: CallApiFn = useCallback(async (method, url, body) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) {
        let msg = `${method} ${url} → ${r.status}`;
        try {
          const j = await r.json();
          if (j?.detail?.code) msg = `${j.detail.code}`;
          else if (typeof j?.detail === "string") msg = j.detail;
        } catch {
          // ignore
        }
        setError(msg);
        return { ok: false, error: msg };
      }
      const data = r.status === 204 ? null : await r.json();
      return { ok: true, data };
    } finally {
      setBusy(false);
    }
  }, []);

  async function setMarkup(value: string) {
    if (!currentRev) return;
    const num = Number(value);
    if (!Number.isFinite(num) || num < 0) return;
    const r = await callApi("PATCH", `/api/revisions/${currentRev.revision_id}`, { markup_pct: num });
    if (r.ok) await refresh();
  }

  async function advance() {
    if (!currentRev) return;
    const r = await callApi("POST", `/api/revisions/${currentRev.revision_id}/advance`, {});
    if (r.ok) await refresh();
  }

  async function accept() {
    if (!currentRev) return;
    const r = await callApi("POST", `/api/revisions/${currentRev.revision_id}/accept`, {});
    if (r.ok) await refresh();
  }

  async function reject() {
    if (!currentRev) return;
    const reason = window.prompt("Reason for rejection?");
    if (!reason) return;
    const r = await callApi("POST", `/api/revisions/${currentRev.revision_id}/reject`, {
      lost_reason: reason,
    });
    if (r.ok) await refresh();
  }

  async function withdraw() {
    if (!currentRev) return;
    const r = await callApi("POST", `/api/revisions/${currentRev.revision_id}/withdraw`, {
      lost_reason: null,
    });
    if (r.ok) await refresh();
  }

  async function expire() {
    if (!currentRev) return;
    const reason = window.prompt("Reason for expiry? (optional)");
    if (reason === null) return;
    const r = await callApi("POST", `/api/revisions/${currentRev.revision_id}/expire`, {
      lost_reason: reason || null,
    });
    if (r.ok) await refresh();
  }

  async function revise() {
    const r = await callApi("POST", `/api/estimates/${estimate.estimate_id}/revise`);
    if (r.ok) await refresh();
  }

  async function doConvert(includeLineIds: number[]) {
    if (!currentRev) return;
    setShowConvert(false);
    const r = await callApi(
      "POST",
      `/api/revisions/${currentRev.revision_id}/convert`,
      { include_line_ids: includeLineIds },
    );
    if (r.ok && r.data && typeof r.data === "object" && "project_id" in r.data) {
      const pid = (r.data as { project_id: number }).project_id;
      router.push(`/projects/${pid}`);
    }
  }

  async function openOrderPreview() {
    if (!currentRev) return;
    const r = await callApi("GET", `/api/revisions/${currentRev.revision_id}/order-preview`);
    if (r.ok) setOrderPreview(r.data as OrderPreview);
  }

  async function confirmGenerateOrders(includeLineIds: number[]) {
    if (!currentRev) return;
    // Close before awaiting, same as doConvert() — on failure (e.g. a
    // stale preview racing a second tab's already-completed generation)
    // this leaves the top-level error banner visible instead of hidden
    // behind the still-open modal.
    setOrderPreview(null);
    const r = await callApi(
      "POST",
      `/api/revisions/${currentRev.revision_id}/generate-orders`,
      { include_line_ids: includeLineIds },
    );
    if (r.ok) {
      setGenerateResult(r.data as GenerateOrdersResult);
      await refresh();
    }
  }

  async function reorderLines(orderedLineIds: number[]) {
    if (!currentRev) return;
    const r = await callApi(
      "POST",
      `/api/revisions/${currentRev.revision_id}/lines/reorder`,
      { ordered_line_ids: orderedLineIds },
    );
    if (r.ok) await refresh();
  }

  async function cloneLine(line: Line) {
    if (!currentRev || !canWrite || !isDraft) return;
    if (!window.confirm(`Clone "${line.description}" with all parts/hardware/labour?`)) return;
    const create = await callApi("POST", `/api/revisions/${currentRev.revision_id}/lines`, {
      description: `${line.description} (copy)`,
      qty: parseFloat(line.qty) || 1,
      unit: line.unit,
      notes: line.notes ?? undefined,
    });
    if (!create.ok || !create.data) return;
    const newLineId = (create.data as { line_id: number }).line_id;
    for (const p of line.parts) {
      if (p.material_id == null) continue;
      await callApi("POST", `/api/lines/${newLineId}/parts`, {
        material_type: p.material_type,
        material_id: p.material_id,
        qty: parseFloat(p.qty) || 1,
        len_mm: p.len_mm ?? undefined,
        wid_mm: p.wid_mm ?? undefined,
        paint_instruction: p.paint_instruction,
        comment: p.comment ?? undefined,
      });
    }
    for (const h of line.hardware) {
      if (h.material_id == null) continue;
      await callApi("POST", `/api/lines/${newLineId}/hardware`, {
        material_type: h.material_type,
        material_id: h.material_id,
        qty: parseFloat(h.qty) || 1,
        comment: h.comment ?? undefined,
      });
    }
    for (const l of line.labour) {
      const hours = parseFloat(l.hours);
      if (!hours) continue;
      await callApi("POST", `/api/lines/${newLineId}/labour`, {
        stage_key: l.stage_key,
        hours,
      });
    }
    await refresh();
  }

  const lines = selectedRev?.lines ?? [];

  function selectRevision(rid: number | null) {
    const next = new URLSearchParams(sp.toString());
    if (rid == null || rid === currentRev?.revision_id) {
      next.delete("rev");
    } else {
      next.set("rev", String(rid));
    }
    router.replace(`/estimating/${estimate.estimate_id}?${next.toString()}`);
  }

  async function setExpiresAt(value: string) {
    if (!currentRev) return;
    const r = await callApi("PATCH", `/api/revisions/${currentRev.revision_id}`, {
      expires_at: value || null,
    });
    if (r.ok) await refresh();
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Link href="/estimating" className="text-xs uppercase tracking-wide text-h-muted hover:text-h-ink">
            ← Estimating
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-h-ink">{estimate.title}</h1>
          <p className="mt-1 font-mono text-sm text-h-muted">
            {estimate.estimate_no} · v{selectedRev?.rev_no ?? "?"} ·{" "}
            <span className="text-h-ink">{estimate.customer.name}</span>
            {estimate.site_address ? <span className="text-h-muted"> · {estimate.site_address}</span> : null}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {selectedRev?.status ? (
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${STATUS_COLOURS[selectedRev.status]}`}
              data-testid="status-pill"
            >
              {selectedRev.status}
            </span>
          ) : null}
          {selectedRev?.status === "SUBMITTED" && isViewingCurrent && canWrite ? (
            <label className="flex items-center gap-1 text-xs text-h-muted">
              <span>Expires</span>
              <input
                type="date"
                defaultValue={selectedRev.expires_at ?? ""}
                onBlur={(e) => setExpiresAt(e.target.value)}
                className="rounded border border-h-line bg-white px-2 py-1 text-xs"
                data-testid="expires-at-input"
              />
            </label>
          ) : null}
          {selectedRev ? (
            <a
              href={`/api/revisions/${selectedRev.revision_id}/quote.pdf`}
              target="_blank"
              rel="noreferrer"
              className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
              data-testid="quote-pdf-link"
            >
              Quote PDF
            </a>
          ) : null}
        </div>
      </div>

      {!isViewingCurrent && selectedRev && currentRev ? (
        <div
          className="flex items-center gap-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          data-testid="locked-snapshot-banner"
        >
          <span>
            Read-only snapshot of v{selectedRev.rev_no}. Current revision is v{currentRev.rev_no}.
          </span>
          <button
            type="button"
            onClick={() => selectRevision(null)}
            className="ml-auto rounded border border-amber-300 bg-white px-2 py-0.5 text-xs hover:bg-amber-100"
            data-testid="back-to-current"
          >
            Back to current
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="api-error">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard label="Subtotal (cost)" value={fmtMoney(selectedRev?.subtotal_cost)} />
        <SummaryCard label="Subtotal (sell)" value={fmtMoney(selectedRev?.subtotal_sell)} />
        <SummaryCard label="Total inc. GST" value={fmtMoney(selectedRev?.total_inc_gst)} bold />
      </div>

      {estimate.revisions.length > 1 ? (
        <RevisionRail
          revisions={estimate.revisions}
          currentId={currentRev?.revision_id ?? null}
          selectedId={selectedRev?.revision_id ?? null}
          onSelect={selectRevision}
        />
      ) : null}

      {canWrite && isDraft ? (
        <div className="flex flex-wrap items-center gap-3 rounded border border-h-line bg-h-surface p-3">
          <label className="text-sm text-h-muted">Markup %</label>
          <input
            type="number"
            min={0}
            step="0.01"
            defaultValue={currentRev?.markup_pct ?? "0"}
            onBlur={(e) => setMarkup(e.target.value)}
            className="w-24 rounded border border-h-line bg-white px-2 py-1 text-sm"
            data-testid="markup-input"
          />
          <button
            type="button"
            onClick={withdraw}
            disabled={busy}
            className="ml-auto rounded border border-h-line bg-white px-3 py-1.5 text-sm font-medium hover:bg-gray-100 disabled:opacity-50"
            data-testid="withdraw-btn"
          >
            Withdraw
          </button>
          <button
            type="button"
            onClick={advance}
            disabled={busy || (nextStageLabel(currentRev?.status) === "Submitted" && lines.length === 0)}
            className="rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="advance-btn"
          >
            {nextStageLabel(currentRev?.status) === "Submitted"
              ? "Lock & send"
              : `Advance → ${nextStageLabel(currentRev?.status) ?? "…"}`}
          </button>
        </div>
      ) : null}

      {canWrite && isViewingCurrent && currentRev?.status === "SUBMITTED" ? (
        <div className="flex gap-2 rounded border border-blue-200 bg-blue-50 p-3 text-sm">
          <button
            type="button"
            onClick={accept}
            disabled={busy}
            className="rounded bg-green-700 px-3 py-1.5 font-medium text-white hover:opacity-90 disabled:opacity-50"
            data-testid="accept-btn"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={reject}
            disabled={busy}
            className="rounded bg-red-700 px-3 py-1.5 font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={withdraw}
            disabled={busy}
            className="rounded border border-h-line bg-white px-3 py-1.5 font-medium hover:bg-gray-100 disabled:opacity-50"
          >
            Withdraw
          </button>
          <button
            type="button"
            onClick={expire}
            disabled={busy}
            className="rounded border border-amber-300 bg-amber-50 px-3 py-1.5 font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
            data-testid="expire-btn"
          >
            Expire
          </button>
          <button
            type="button"
            onClick={revise}
            disabled={busy}
            className="ml-auto rounded border border-h-line bg-white px-3 py-1.5 font-medium hover:bg-gray-100 disabled:opacity-50"
          >
            Revise (new draft)
          </button>
        </div>
      ) : null}

      {canWrite && isViewingCurrent && currentRev?.status === "WON" && !currentRev?.converted_project_id ? (
        <div className="flex items-center gap-3 rounded border border-green-200 bg-green-50 p-3">
          <span className="text-sm text-green-900">Ready to materialise into a real project.</span>
          <button
            type="button"
            onClick={() => setShowConvert(true)}
            disabled={busy}
            className="ml-auto rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="convert-btn"
          >
            Convert to project
          </button>
        </div>
      ) : null}

      <DraggableLineList
        lines={lines}
        isDraft={!!isDraft && canWrite}
        catalogs={catalogs}
        onReorder={reorderLines}
        onChanged={refresh}
        onClone={cloneLine}
        callApi={callApi}
      />

      {isDraft && canWrite && currentRev ? (
        <NewLineForm revisionId={currentRev.revision_id} callApi={callApi} onCreated={refresh} />
      ) : null}

      {showConvert && currentRev ? (
        <ConvertPreviewDialog
          estimateNo={estimate.estimate_no}
          lines={currentRev.lines}
          busy={busy}
          onConfirm={doConvert}
          onCancel={() => setShowConvert(false)}
        />
      ) : null}

      {canWrite && isViewingCurrent && currentRev?.converted_project_id
      && (pendingOrderLines > 0 || dismissedOrderLines > 0) ? (
        <div className="flex items-center gap-3 rounded border border-blue-200 bg-blue-50 p-3">
          <span className="text-sm text-blue-900" data-testid="orders-bar-text">
            {pendingOrderLines === 0
              ? `${dismissedOrderLines} line${dismissedOrderLines === 1 ? "" : "s"} marked ordered by hand.`
              : currentRev.orders_generated_at || dismissedOrderLines > 0
                ? `${pendingOrderLines} line${pendingOrderLines === 1 ? "" : "s"} not yet ordered from this quote.`
                : "Converted — materials can now be ordered from this quote."}
            {pendingOrderLines > 0 && dismissedOrderLines > 0
              ? ` ${dismissedOrderLines} marked ordered by hand.`
              : ""}
          </span>
          <button
            type="button"
            onClick={openOrderPreview}
            disabled={busy}
            className="ml-auto rounded bg-blue-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="generate-orders-btn"
          >
            {pendingOrderLines > 0 ? "Generate orders" : "Review lines"}
          </button>
        </div>
      ) : null}

      {currentRev?.orders_generated_at ? (
        <div className="rounded border border-h-line bg-h-surface p-3 text-sm text-h-muted">
          Orders {pendingOrderLines > 0 ? "last " : ""}generated {new Date(currentRev.orders_generated_at).toLocaleString()}
          {currentRev.converted_project_id ? (
            <>
              {" — see "}
              <Link href={`/orderbook`} className="text-h-accent underline">
                the Orderbook
              </Link>
              {"."}
            </>
          ) : null}
        </div>
      ) : null}

      {generateResult ? (
        <div className="rounded border border-green-200 bg-green-50 p-3 text-sm text-green-900">
          <span>{summariseGenerateResult(generateResult)}</span>{" "}
          <Link href="/orderbook" className="underline">Open the Orderbook →</Link>
        </div>
      ) : null}

      {orderPreview ? (
        <OrderPreviewDialog
          preview={orderPreview}
          busy={busy}
          onConfirm={confirmGenerateOrders}
          onCancel={() => setOrderPreview(null)}
          onChanged={refresh}
        />
      ) : null}
    </section>
  );
}

interface ConvertPreviewDialogProps {
  estimateNo: string;
  lines: Line[];
  busy: boolean;
  onConfirm: (includeLineIds: number[]) => void;
  onCancel: () => void;
}

function ConvertPreviewDialog({
  estimateNo, lines, busy, onConfirm, onCancel,
}: ConvertPreviewDialogProps) {
  // Q490's PM review-and-select screen: every line starts selected (nothing
  // re-entered that's already known), and deselecting one just means it
  // doesn't become a Joinery Item — the rest of the handover is unaffected.
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(lines.map((l) => l.line_id)),
  );
  const selectedLines = lines.filter((l) => selected.has(l.line_id));
  const items = selectedLines.length;
  const parts = selectedLines.reduce((acc, l) => acc + l.parts.length, 0);
  const hardware = selectedLines.reduce((acc, l) => acc + l.hardware.length, 0);
  const labour = selectedLines.reduce(
    (acc, l) => acc + l.labour.filter((x) => parseFloat(x.hours) > 0).length, 0,
  );

  function toggle(lineId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div
        className="w-full max-w-md space-y-3 rounded border border-h-line bg-white p-5 shadow-xl"
        data-testid="convert-preview-dialog"
      >
        <h2 className="text-lg font-semibold text-h-ink">
          Convert {estimateNo} to project
        </h2>
        <p className="text-sm text-h-muted">
          Choose which lines become Joinery Items. This materialises the
          selection into items, parts, hardware lines, and labour
          assignments. The new project will reference this revision.
        </p>
        <ul className="max-h-48 space-y-1 overflow-y-auto rounded border border-h-line p-2 text-sm">
          {lines.map((l) => (
            <li key={l.line_id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(l.line_id)}
                onChange={() => toggle(l.line_id)}
                data-testid={`convert-line-${l.line_id}`}
              />
              <span className="flex-1">{l.description}</span>
              <span className="font-mono text-h-muted">{fmtMoney(l.total_sell)}</span>
            </li>
          ))}
        </ul>
        <dl className="grid grid-cols-2 gap-y-2 rounded border border-h-line bg-h-surface p-3 text-sm">
          <dt className="text-h-muted">Items to create</dt>
          <dd className="text-right font-mono">{items}</dd>
          <dt className="text-h-muted">Parts</dt>
          <dd className="text-right font-mono">{parts}</dd>
          <dt className="text-h-muted">Hardware lines</dt>
          <dd className="text-right font-mono">{hardware}</dd>
          <dt className="text-h-muted">Labour assignments</dt>
          <dd className="text-right font-mono">{labour}</dd>
        </dl>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(Array.from(selected))}
            disabled={busy || selected.size === 0}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="convert-confirm-btn"
          >
            {busy ? "Converting…" : "Convert"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface OrderPreviewDialogProps {
  preview: OrderPreview;
  busy: boolean;
  onConfirm: (includeLineIds: number[]) => void;
  onCancel: () => void;
  /** A line was marked / un-marked "ordered by hand": the page's own counts are stale. */
  onChanged?: () => void;
}

function OrderPreviewDialog({ preview: initial, busy, onConfirm, onCancel, onChanged }: OrderPreviewDialogProps) {
  // The quote lines to order now are the PM's choice; the supplier groups below
  // are always the server's answer for exactly that selection, so ticking a line
  // re-asks it. Lines an earlier run covered stay visible but cannot be ticked.
  const [preview, setPreview] = useState(initial);
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(initial.lines.filter((l) => l.selected).map((l) => l.line_id)),
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  // Several quick ticks fire several requests; only the newest may write.
  const refreshSeq = useRef(0);

  // For the "Link supplier" shortcut on an unassigned material. null = not loaded or
  // unreadable (`GET /suppliers` needs orderbook:read): the shortcut is then disabled.
  const [suppliers, setSuppliers] = useState<SupplierOption[] | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linkingKey, setLinkingKey] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listSupplierOptions()
      .then((l) => live && setSuppliers(l))
      .catch(() => live && setSuppliers(null));
    return () => {
      live = false;
    };
  }, []);

  // "Ordered by hand": a line the PM ordered outside the system leaves the pending set.
  // One line at a time (`dismissing`), a required reason, and it can be undone.
  const [dismissing, setDismissing] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [lineBusy, setLineBusy] = useState(false);
  const [lineError, setLineError] = useState<string | null>(null);

  // After either change the server decides which lines are pending: re-read them (a
  // default preview carries every line's current state), keep the PM's own ticks that
  // are still valid, and re-ask for the groups of that selection.
  async function afterLineChange(lineId: number, restored: boolean) {
    const mine = ++refreshSeq.current;
    try {
      const r = await fetch(`/api/revisions/${preview.revision_id}/order-preview`);
      if (mine !== refreshSeq.current) return;
      if (!r.ok) throw new Error(`order-preview → ${r.status}`);
      const fresh = (await r.json()) as OrderPreview;
      const pending = new Set(fresh.lines.filter((l) => l.selected).map((l) => l.line_id));
      const next = new Set<number>();
      selected.forEach((id) => pending.has(id) && next.add(id));
      if (restored && pending.has(lineId)) next.add(lineId);
      setSelected(next);
      setPreview({ ...fresh, groups: [], unassigned: [] });
      setRefreshError(null);
      if (next.size > 0) await refreshFor(next);
    } catch (e) {
      if (mine !== refreshSeq.current) return;
      setRefreshError(e instanceof Error ? e.message : "Could not refresh the preview");
    }
    onChanged?.();
  }

  async function changeLine(lineId: number, method: "POST" | "DELETE") {
    setLineBusy(true);
    setLineError(null);
    try {
      const r = await fetch(
        `/api/revisions/${preview.revision_id}/lines/${lineId}/order-dismissal`,
        method === "POST"
          ? {
              method,
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ reason: reason.trim() }),
            }
          : { method },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        const code = body?.detail?.code;
        setLineError(
          code === "ALREADY_GENERATED"
            ? "A run has already ordered this line — refreshing."
            : code === "ALREADY_DISMISSED"
              ? "Someone already marked this line ordered by hand — refreshing."
              : code === "NOT_DISMISSED"
                ? "This line is no longer marked ordered by hand — refreshing."
                : `Could not ${method === "POST" ? "mark" : "undo"} the line (${r.status}).`,
        );
      } else {
        setDismissing(null);
        setReason("");
      }
      // Either way the server's answer is the truth now.
      await afterLineChange(lineId, method === "DELETE");
    } catch {
      setLineError("Could not reach the server — nothing was changed.");
    } finally {
      setLineBusy(false);
    }
  }

  function toggle(lineId: number) {
    const next = new Set(selected);
    if (next.has(lineId)) next.delete(lineId);
    else next.add(lineId);
    setSelected(next);
    return refreshFor(next);
  }

  async function refreshFor(next: Set<number>) {
    const mine = ++refreshSeq.current;
    setRefreshError(null);
    if (next.size === 0) {
      // Nothing selected cannot be asked of the API (no ids means "all pending").
      setRefreshing(false);
      setPreview((p) => ({ ...p, groups: [], unassigned: [] }));
      return;
    }
    setRefreshing(true);
    try {
      const qs = Array.from(next).map((id) => `include_line_ids=${id}`).join("&");
      const r = await fetch(`/api/revisions/${preview.revision_id}/order-preview?${qs}`);
      if (mine !== refreshSeq.current) return;
      if (!r.ok) throw new Error(`order-preview → ${r.status}`);
      setPreview((await r.json()) as OrderPreview);
    } catch (e) {
      if (mine !== refreshSeq.current) return;
      setRefreshError(e instanceof Error ? e.message : "Could not refresh the preview");
    } finally {
      if (mine === refreshSeq.current) setRefreshing(false);
    }
  }

  // Give a supplier-less material its supplier (the narrow estimating route, not the
  // Catalog's), then re-ask the server: the material leaves "no supplier" and its
  // held-back lines become orderable.
  async function linkSupplier(material: OrderPreviewLine, supplierId: number) {
    const key = `${material.material_type}-${material.material_id}`;
    setLinkingKey(key);
    setLinkError(null);
    try {
      const r = await fetch(`/api/revisions/${preview.revision_id}/link-supplier`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          material_type: material.material_type,
          material_id: material.material_id,
          supplier_id: supplierId,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        const code = body?.detail?.code;
        setLinkError(
          code === "ALREADY_LINKED"
            ? "Someone already linked a supplier to this material — refreshing."
            : code === "UNKNOWN_SUPPLIER"
              ? "That supplier is no longer available."
              : `Could not link the supplier (${r.status}).`,
        );
      }
      // Either way the server's answer is the truth now.
      if (selected.size > 0) await refreshFor(selected);
    } catch {
      setLinkError("Could not link the supplier (network error).");
    } finally {
      setLinkingKey(null);
    }
  }

  const ready = !busy && !refreshing && !refreshError && selected.size > 0
    && (preview.groups.length > 0 || preview.unassigned.length === 0);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div
        className="w-full max-w-lg space-y-3 rounded border border-h-line bg-white p-5 shadow-xl"
        data-testid="order-preview-dialog"
      >
        <h2 className="text-lg font-semibold text-h-ink">Generate orders</h2>
        <p className="text-sm text-h-muted">
          Tick the quote lines to order now — the rest can be generated later.
          One draft purchase order per supplier is made from the ticked lines&apos;
          material breakdown at today&apos;s catalog pricing. Review before
          creating them — each PO can still be edited in the Orderbook
          afterwards.
        </p>
        <ul
          className="max-h-36 space-y-1 overflow-y-auto rounded border border-h-line p-2 text-sm"
          data-testid="order-preview-lines"
        >
          {preview.lines.map((l) => {
            const covered = l.orders_generated_at != null;
            const byHand = l.orders_dismissed_at != null;
            const done = covered || byHand;
            return (
              <li key={l.line_id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(l.line_id)}
                  disabled={done}
                  onChange={() => toggle(l.line_id)}
                  data-testid={`order-line-${l.line_id}`}
                />
                <span className={`flex-1 ${done ? "text-h-muted" : ""}`}>{l.description}</span>
                {l.held_back && selected.has(l.line_id) ? (
                  <span
                    className="whitespace-nowrap rounded-full border border-amber-300 bg-amber-50 px-1.5 text-xs text-amber-900"
                    data-testid={`order-line-held-${l.line_id}`}
                  >
                    held back — no supplier
                  </span>
                ) : null}
                <span
                  className="whitespace-nowrap text-xs text-h-muted"
                  data-testid={byHand ? `order-line-byhand-${l.line_id}` : undefined}
                  title={byHand ? (l.orders_dismissed_reason ?? undefined) : undefined}
                >
                  {covered
                    ? `ordered ${new Date(l.orders_generated_at as string).toLocaleDateString()}`
                    : byHand
                      ? `ordered by hand ${new Date(l.orders_dismissed_at as string).toLocaleDateString()}`
                        + (l.orders_dismissed_by_name ? ` by ${l.orders_dismissed_by_name}` : "")
                        + (l.orders_dismissed_reason ? ` — ${l.orders_dismissed_reason}` : "")
                      : `× ${l.qty} ${l.unit}`}
                </span>
                {byHand ? (
                  <button
                    type="button"
                    onClick={() => void changeLine(l.line_id, "DELETE")}
                    disabled={lineBusy}
                    className="whitespace-nowrap text-xs text-h-accent underline disabled:opacity-50"
                    data-testid={`undo-dismiss-${l.line_id}`}
                  >
                    Undo
                  </button>
                ) : !covered ? (
                  <button
                    type="button"
                    onClick={() => {
                      setDismissing(dismissing === l.line_id ? null : l.line_id);
                      setReason("");
                      setLineError(null);
                    }}
                    disabled={lineBusy}
                    className="whitespace-nowrap text-xs text-h-accent underline disabled:opacity-50"
                    data-testid={`dismiss-line-${l.line_id}`}
                  >
                    Ordered by hand…
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
        {dismissing !== null ? (
          <form
            className="space-y-2 rounded border border-h-line bg-h-bg p-2 text-sm"
            data-testid="dismiss-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (reason.trim()) void changeLine(dismissing, "POST");
            }}
          >
            <label className="block text-xs text-h-muted" htmlFor="dismiss-reason">
              How was it ordered? (required — nothing in the system can see this order, so
              this note is the only record)
            </label>
            <input
              id="dismiss-reason"
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. ordered by phone from Plyco, PO 1234"
              className="w-full rounded border border-h-line bg-white px-2 py-1"
              data-testid="dismiss-reason"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={lineBusy || !reason.trim()}
                className="rounded bg-h-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                data-testid="dismiss-save"
              >
                {lineBusy ? "Saving…" : "Mark ordered by hand"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDismissing(null);
                  setReason("");
                }}
                className="rounded border border-h-line px-3 py-1 text-xs text-h-muted"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : null}
        {lineError ? (
          <p className="text-sm text-red-800" data-testid="dismiss-error">
            {lineError}
          </p>
        ) : null}
        {refreshError ? (
          <p className="text-sm text-red-800" data-testid="order-preview-error">
            Could not refresh the preview ({refreshError}). Tick a line again to retry.
          </p>
        ) : null}
        <div
          className={`max-h-72 space-y-3 overflow-y-auto ${refreshing ? "opacity-50" : ""}`}
          data-testid="order-preview-groups"
        >
          {preview.groups.length === 0 ? (
            <p className="text-sm text-h-muted">
              {selected.size === 0
                ? "No lines ticked."
                : "Nothing to order — no ticked line has a real material link."}
            </p>
          ) : (
            preview.groups.map((g) => (
              <div key={g.supplier_id} className="rounded border border-h-line p-3" data-testid="order-preview-group">
                <div className="mb-1 flex items-center justify-between text-sm font-medium text-h-ink">
                  <span>{g.supplier_name ?? `Vendor #${g.supplier_id}`}</span>
                  <span className="rounded-full border border-h-line px-1.5 py-0.5 text-xs text-h-muted">
                    {g.category}
                  </span>
                </div>
                <ul className="space-y-0.5 text-xs text-h-muted">
                  {g.lines.map((l) => (
                    <li key={`${l.material_type}-${l.material_id}`} className="flex justify-between gap-2">
                      <span className="truncate">
                        {l.description ?? l.sku ?? "material"} × {l.qty} {l.unit}
                        {l.archived ? " (archived in catalog)" : ""}
                      </span>
                      <span className="font-mono whitespace-nowrap">{fmtMoney(l.unit_cost)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
          {preview.unassigned.length > 0 ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3">
              <div className="mb-1 text-sm font-medium text-amber-900">
                No default supplier — the lines using these are held back whole. Link a
                supplier here (or in the Catalog) and they become orderable
              </div>
              <ul className="space-y-0.5 text-xs text-amber-900">
                {preview.unassigned.map((l) => {
                  const key = `${l.material_type}-${l.material_id}`;
                  return (
                    <li key={key} className="flex items-center justify-between gap-2 py-0.5">
                      <span className="truncate">
                        {l.description ?? l.sku ?? "material"} × {l.qty} {l.unit}
                      </span>
                      <select
                        aria-label={`Link supplier for ${l.description ?? l.sku ?? "material"}`}
                        data-testid={`link-supplier-${key}`}
                        value=""
                        disabled={suppliers == null || linkingKey != null || refreshing}
                        onChange={(e) => {
                          if (e.target.value) void linkSupplier(l, Number(e.target.value));
                        }}
                        className="max-w-[10rem] rounded border border-amber-300 bg-white px-1 py-0.5 text-xs text-amber-900"
                      >
                        <option value="">{linkingKey === key ? "Linking…" : "Link supplier…"}</option>
                        {(suppliers ?? []).map((sp) => (
                          <option key={sp.vendor_id} value={sp.vendor_id}>{sp.name}</option>
                        ))}
                      </select>
                    </li>
                  );
                })}
              </ul>
              {linkError ? (
                <p className="mt-1 text-xs text-red-800" data-testid="link-supplier-error">{linkError}</p>
              ) : null}
              {suppliers == null ? (
                <p className="mt-1 text-xs text-amber-900">
                  The supplier list couldn&apos;t be read, so suppliers can&apos;t be linked from here.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
        {!refreshing && !refreshError && selected.size > 0
          && preview.groups.length === 0 && preview.unassigned.length > 0 ? (
          <p className="text-sm text-amber-900" data-testid="order-preview-nothing-orderable">
            Nothing can be generated yet — every ticked line uses a material with no
            supplier. Link a supplier to each material above (or in the Catalog); the lines
            stay orderable.
          </p>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(Array.from(selected))}
            disabled={!ready}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="generate-orders-confirm-btn"
          >
            {busy
              ? "Generating…"
              : preview.groups.length === 0
                ? "Mark ticked lines done (nothing to order)"
                : `Generate ${preview.groups.length} order${preview.groups.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="rounded border border-h-line bg-h-surface p-3">
      <div className="text-xs uppercase tracking-wide text-h-muted">{label}</div>
      <div
        className={`mt-1 font-mono ${bold ? "text-xl font-semibold text-h-ink" : "text-lg text-h-ink"}`}
        data-testid={`summary-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
      >
        {value}
      </div>
    </div>
  );
}

interface NewLineFormProps {
  revisionId: number;
  callApi: CallApiFn;
  onCreated: () => Promise<void>;
}

function NewLineForm({ revisionId, callApi, onCreated }: NewLineFormProps) {
  const [description, setDescription] = useState("");
  const [qty, setQty] = useState("1");
  const [unit, setUnit] = useState("EA");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const qtyNum = Number(qty);
    if (!description.trim() || !Number.isFinite(qtyNum) || qtyNum <= 0) return;
    setSubmitting(true);
    const r = await callApi("POST", `/api/revisions/${revisionId}/lines`, {
      description: description.trim(),
      qty: qtyNum,
      unit: unit.trim() || "EA",
    });
    setSubmitting(false);
    if (r.ok) {
      setDescription("");
      setQty("1");
      setUnit("EA");
      await onCreated();
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-2 rounded border border-dashed border-h-line bg-white p-3"
      data-testid="new-line-form"
    >
      <div className="flex-1 min-w-[200px]">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
          placeholder="Kitchen island cabinet"
          className="mt-1 w-full rounded border border-h-line px-2 py-1 text-sm"
          data-testid="new-line-description"
        />
      </div>
      <div className="w-24">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Qty</label>
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="mt-1 w-full rounded border border-h-line px-2 py-1 font-mono text-sm"
          data-testid="new-line-qty"
        />
      </div>
      <div className="w-20">
        <label className="block text-xs uppercase tracking-wide text-h-muted">Unit</label>
        <input
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="mt-1 w-full rounded border border-h-line px-2 py-1 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
        data-testid="new-line-submit"
      >
        + Add line
      </button>
    </form>
  );
}

interface DraggableLineListProps {
  lines: Line[];
  isDraft: boolean;
  catalogs: CatalogMap;
  onReorder: (orderedLineIds: number[]) => Promise<void>;
  onChanged: () => Promise<void>;
  onClone: (line: Line) => Promise<void>;
  callApi: CallApiFn;
}

function DraggableLineList({
  lines, isDraft, catalogs, onReorder, onChanged, onClone, callApi,
}: DraggableLineListProps) {
  const [draggedId, setDraggedId] = useState<number | null>(null);

  function handleDragStart(lid: number) {
    setDraggedId(lid);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  async function handleDrop(targetLid: number) {
    if (draggedId == null || draggedId === targetLid) {
      setDraggedId(null);
      return;
    }
    const ids = lines.map((l) => l.line_id);
    const fromIdx = ids.indexOf(draggedId);
    const toIdx = ids.indexOf(targetLid);
    if (fromIdx < 0 || toIdx < 0) {
      setDraggedId(null);
      return;
    }
    const next = [...ids];
    next.splice(fromIdx, 1);
    next.splice(toIdx, 0, draggedId);
    setDraggedId(null);
    await onReorder(next);
  }

  return (
    <div className="space-y-3" data-testid="lines-list">
      {lines.map((line) => (
        <div
          key={line.line_id}
          draggable={isDraft}
          onDragStart={() => handleDragStart(line.line_id)}
          onDragOver={handleDragOver}
          onDrop={() => handleDrop(line.line_id)}
          className={draggedId === line.line_id ? "opacity-50" : ""}
        >
          <LineCard
            line={line}
            isDraft={isDraft}
            catalogs={catalogs}
            onChanged={onChanged}
            onClone={onClone}
            callApi={callApi}
          />
        </div>
      ))}
    </div>
  );
}

interface LineCardProps {
  line: Line;
  isDraft: boolean;
  catalogs: CatalogMap;
  onChanged: () => Promise<void>;
  onClone: (line: Line) => Promise<void>;
  callApi: CallApiFn;
}

function LineCard({ line, isDraft, catalogs, onChanged, onClone, callApi }: LineCardProps) {
  const [showPicker, setShowPicker] = useState(false);
  const [showLabour, setShowLabour] = useState(false);
  const [editing, setEditing] = useState(false);

  async function addFromPicker(payload: PickerPayload) {
    if (isPartKind(payload.kind)) {
      const r = await callApi("POST", `/api/lines/${line.line_id}/parts`, {
        material_type: payload.kind,
        material_id: payload.material_id,
        qty: payload.qty,
        len_mm: payload.len_mm ?? undefined,
        wid_mm: payload.wid_mm ?? undefined,
        paint_instruction: payload.paint_instruction,
        comment: payload.comment ?? undefined,
      });
      if (r.ok) {
        await onChanged();
        setShowPicker(false);
      }
    } else {
      const r = await callApi("POST", `/api/lines/${line.line_id}/hardware`, {
        material_type: payload.kind,
        material_id: payload.material_id,
        qty: payload.qty,
        comment: payload.comment ?? undefined,
      });
      if (r.ok) {
        await onChanged();
        setShowPicker(false);
      }
    }
  }

  async function setLabour(stage: StageKey, hours: number) {
    const r = await callApi("POST", `/api/lines/${line.line_id}/labour`, {
      stage_key: stage,
      hours,
    });
    if (r.ok) await onChanged();
  }

  async function deleteLine() {
    if (!window.confirm(`Delete line "${line.description}"?`)) return;
    const r = await callApi("DELETE", `/api/lines/${line.line_id}`);
    if (r.ok) await onChanged();
  }

  async function patchPart(p: LinePart, qty: number) {
    if (!Number.isFinite(qty) || qty <= 0) return;
    const r = await callApi("PATCH", `/api/estimate-parts/${p.part_id}`, { qty });
    if (r.ok) await onChanged();
  }

  async function removePart(p: LinePart) {
    const r = await callApi("DELETE", `/api/estimate-parts/${p.part_id}`);
    if (r.ok) await onChanged();
  }

  async function patchHardware(h: LineHardware, qty: number) {
    if (!Number.isFinite(qty) || qty <= 0) return;
    const r = await callApi("PATCH", `/api/hardware/${h.hw_id}`, { qty });
    if (r.ok) await onChanged();
  }

  async function removeHardware(h: LineHardware) {
    const r = await callApi("DELETE", `/api/hardware/${h.hw_id}`);
    if (r.ok) await onChanged();
  }

  return (
    <div
      className="rounded border border-h-line bg-h-surface p-4"
      data-testid={`line-card-${line.line_id}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          {isDraft ? (
            <span className="cursor-move text-h-muted" title="Drag to reorder">⋮⋮</span>
          ) : null}
          <span className="text-xs font-mono text-h-muted">#{line.seq}</span>
          {editing ? null : (
            <span className="font-medium text-h-ink">{line.description}</span>
          )}
        </div>
        <div className="text-right">
          <div className="font-mono text-sm text-h-ink">{fmtMoney(line.total_sell)}</div>
          <div className="font-mono text-xs text-h-muted">
            {parseFloat(line.qty)} {line.unit} × {fmtMoney(line.unit_sell)}
          </div>
        </div>
      </div>

      {editing && isDraft ? (
        <LineEditRow
          line={line}
          callApi={callApi}
          onSaved={async () => { setEditing(false); await onChanged(); }}
          onCancel={() => setEditing(false)}
        />
      ) : null}

      <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-h-muted">
        <span>Material: {fmtMoney(line.material_cost)}</span>
        <span>Labour: {fmtMoney(line.labour_cost)}</span>
        <span>Total cost: {fmtMoney(line.total_cost)}</span>
      </div>

      {line.parts.length > 0 || line.hardware.length > 0 || line.labour.length > 0 ? (
        <div className="mt-3 space-y-1 border-t border-h-line pt-3 text-xs">
          {line.parts.map((p) => (
            <PartRow
              key={p.part_id}
              part={p}
              isDraft={isDraft}
              onPatch={(qty) => patchPart(p, qty)}
              onRemove={() => removePart(p)}
            />
          ))}
          {line.hardware.map((h) => (
            <HardwareRow
              key={h.hw_id}
              hardware={h}
              isDraft={isDraft}
              onPatch={(qty) => patchHardware(h, qty)}
              onRemove={() => removeHardware(h)}
            />
          ))}
          {line.labour.map((l) => (
            <div key={l.labour_id} className="flex justify-between gap-2">
              <span>
                <span className="font-mono text-h-muted">{l.stage_key}</span>{" "}
                {parseFloat(l.hours)} hr × {fmtMoney(l.rate_snapshot)}/hr
              </span>
              <span className="flex items-center gap-2">
                <span className="font-mono">{fmtMoney(l.cost_extended)}</span>
                {isDraft ? (
                  <button
                    type="button"
                    onClick={() => setLabour(l.stage_key, 0)}
                    className="text-red-700 hover:text-red-900"
                    title="Remove labour"
                  >
                    ×
                  </button>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {isDraft ? (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-h-line pt-3">
          <button
            type="button"
            onClick={() => setShowPicker((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`add-material-${line.line_id}`}
          >
            + Material
          </button>
          <button
            type="button"
            onClick={() => setShowLabour((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`add-labour-${line.line_id}`}
          >
            + Labour
          </button>
          <button
            type="button"
            onClick={() => setEditing((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`edit-line-${line.line_id}`}
          >
            ✎ Edit
          </button>
          <button
            type="button"
            onClick={() => onClone(line)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`clone-line-${line.line_id}`}
          >
            ⎘ Clone
          </button>
          <button
            type="button"
            onClick={deleteLine}
            className="ml-auto rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-800 hover:bg-red-100"
          >
            Delete line
          </button>
        </div>
      ) : null}

      {showPicker ? (
        <CatalogPicker
          catalogs={catalogs}
          onPick={addFromPicker}
          onClose={() => setShowPicker(false)}
        />
      ) : null}
      {showLabour ? (
        <LabourEditor line={line} onSet={setLabour} onClose={() => setShowLabour(false)} />
      ) : null}
    </div>
  );
}

interface LineEditRowProps {
  line: Line;
  callApi: CallApiFn;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}

function LineEditRow({ line, callApi, onSaved, onCancel }: LineEditRowProps) {
  const [description, setDescription] = useState(line.description);
  const [qty, setQty] = useState(line.qty);
  const [unit, setUnit] = useState(line.unit);
  const [overrideStr, setOverrideStr] = useState(line.unit_sell_override ?? "");

  async function save() {
    const fields: Record<string, unknown> = {};
    if (description !== line.description) fields.description = description;
    const qtyNum = Number(qty);
    if (Number.isFinite(qtyNum) && qtyNum > 0 && String(qtyNum) !== String(parseFloat(line.qty))) {
      fields.qty = qtyNum;
    }
    if (unit !== line.unit) fields.unit = unit;
    if (overrideStr === "") {
      if (line.unit_sell_override !== null) fields.clear_unit_sell_override = true;
    } else {
      const num = Number(overrideStr);
      if (Number.isFinite(num) && num >= 0) fields.unit_sell_override = num;
    }
    if (Object.keys(fields).length === 0) {
      onCancel();
      return;
    }
    const r = await callApi("PATCH", `/api/lines/${line.line_id}`, fields);
    if (r.ok) await onSaved();
  }

  return (
    <div
      className="mt-2 grid grid-cols-1 gap-2 rounded border border-h-line bg-white p-3 text-xs md:grid-cols-4"
      data-testid={`line-edit-${line.line_id}`}
    >
      <label className="md:col-span-2 flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Description</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1"
        />
      </label>
      <label className="flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Qty</span>
        <input
          type="number"
          min="0.01"
          step="0.01"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1 font-mono"
        />
      </label>
      <label className="flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Unit</span>
        <input
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="mt-1 rounded border border-h-line px-2 py-1"
        />
      </label>
      <label className="md:col-span-2 flex flex-col">
        <span className="text-h-muted uppercase tracking-wide">Unit sell override (blank = use markup)</span>
        <input
          type="number"
          min="0"
          step="0.01"
          value={overrideStr ?? ""}
          onChange={(e) => setOverrideStr(e.target.value)}
          placeholder="auto"
          className="mt-1 rounded border border-h-line px-2 py-1 font-mono"
        />
      </label>
      <div className="md:col-span-2 flex items-end justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line bg-white px-3 py-1 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          className="rounded bg-h-accent px-3 py-1 font-medium text-white shadow hover:opacity-90"
          data-testid={`line-edit-save-${line.line_id}`}
        >
          Save
        </button>
      </div>
    </div>
  );
}

interface PartRowProps {
  part: LinePart;
  isDraft: boolean;
  onPatch: (qty: number) => Promise<void>;
  onRemove: () => Promise<void>;
}

function PartRow({ part, isDraft, onPatch, onRemove }: PartRowProps) {
  return (
    <div className="flex justify-between gap-2">
      <span>
        <span className="font-mono text-h-muted">{part.material_type}</span>{" "}
        {part.sku_snapshot} · {part.description_snapshot}
        {part.len_mm || part.wid_mm ? (
          <span className="ml-1 font-mono text-h-muted">
            {part.len_mm ?? "?"}×{part.wid_mm ?? "?"}
          </span>
        ) : null}
      </span>
      <span className="flex items-center gap-2">
        {isDraft ? (
          <input
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={part.qty}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (n !== parseFloat(part.qty)) onPatch(n);
            }}
            className="w-16 rounded border border-h-line px-1 font-mono text-right"
            data-testid={`part-qty-${part.part_id}`}
          />
        ) : (
          <span className="font-mono">{parseFloat(part.qty)}</span>
        )}
        <span className="font-mono">{`$${parseFloat(part.cost_extended).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</span>
        {isDraft ? (
          <button
            type="button"
            onClick={onRemove}
            className="text-red-700 hover:text-red-900"
            title="Remove part"
            data-testid={`remove-part-${part.part_id}`}
          >
            ×
          </button>
        ) : null}
      </span>
    </div>
  );
}

interface HardwareRowProps {
  hardware: LineHardware;
  isDraft: boolean;
  onPatch: (qty: number) => Promise<void>;
  onRemove: () => Promise<void>;
}

function HardwareRow({ hardware, isDraft, onPatch, onRemove }: HardwareRowProps) {
  return (
    <div className="flex justify-between gap-2">
      <span>
        <span className="font-mono text-h-muted">{hardware.material_type}</span>{" "}
        {hardware.sku_snapshot} · {hardware.description_snapshot}
      </span>
      <span className="flex items-center gap-2">
        {isDraft ? (
          <input
            type="number"
            min="0.01"
            step="0.01"
            defaultValue={hardware.qty}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (n !== parseFloat(hardware.qty)) onPatch(n);
            }}
            className="w-16 rounded border border-h-line px-1 font-mono text-right"
            data-testid={`hw-qty-${hardware.hw_id}`}
          />
        ) : (
          <span className="font-mono">{parseFloat(hardware.qty)}</span>
        )}
        <span className="font-mono">{`$${parseFloat(hardware.cost_extended).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</span>
        {isDraft ? (
          <button
            type="button"
            onClick={onRemove}
            className="text-red-700 hover:text-red-900"
            title="Remove hardware"
            data-testid={`remove-hw-${hardware.hw_id}`}
          >
            ×
          </button>
        ) : null}
      </span>
    </div>
  );
}

interface CatalogPickerProps {
  catalogs: CatalogMap;
  onPick: (payload: PickerPayload) => Promise<void>;
  onClose: () => void;
}

function CatalogPicker({ catalogs, onPick, onClose }: CatalogPickerProps) {
  const [kind, setKind] = useState<MaterialKind>("BOARD");
  const [search, setSearch] = useState("");
  const [qty, setQty] = useState("1");
  const [lenMm, setLenMm] = useState("");
  const [widMm, setWidMm] = useState("");
  const [paint, setPaint] = useState<PickerPayload["paint_instruction"]>("NONE");
  const [comment, setComment] = useState("");

  const rows = catalogs[kind] ?? [];
  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter((r) => r.sku.toLowerCase().includes(q) || r.description.toLowerCase().includes(q))
    : rows;

  async function pick(materialId: number) {
    const qtyNum = Number(qty);
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) return;
    const lenNum = lenMm ? Number(lenMm) : null;
    const widNum = widMm ? Number(widMm) : null;
    await onPick({
      kind,
      material_id: materialId,
      qty: qtyNum,
      len_mm: kind === "BOARD" ? lenNum : null,
      wid_mm: kind === "BOARD" ? widNum : null,
      paint_instruction: kind === "BOARD" ? paint : "NONE",
      comment: comment.trim() || undefined,
    });
  }

  return (
    <div className="mt-2 rounded border border-h-line bg-white p-3 text-xs" data-testid="catalog-picker">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex flex-wrap gap-1">
          {ALL_KINDS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`rounded border px-2 py-0.5 ${
                kind === k
                  ? "border-h-accent bg-h-accent text-white"
                  : "border-h-line bg-white hover:bg-gray-50"
              }`}
              data-testid={`picker-kind-${k}`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <button type="button" onClick={onClose} className="text-h-muted hover:text-h-ink">×</button>
      </div>

      <div className="mb-2 flex flex-wrap gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search SKU or description"
          className="flex-1 min-w-[160px] rounded border border-h-line px-2 py-1"
          data-testid="picker-search"
        />
        <label className="flex items-center gap-1">
          <span className="text-h-muted">Qty</span>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-16 rounded border border-h-line px-1 font-mono"
            data-testid="picker-qty"
          />
        </label>
        {kind === "BOARD" ? (
          <>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">L (mm)</span>
              <input
                type="number"
                min="0"
                value={lenMm}
                onChange={(e) => setLenMm(e.target.value)}
                className="w-16 rounded border border-h-line px-1 font-mono"
                data-testid="picker-len"
              />
            </label>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">W (mm)</span>
              <input
                type="number"
                min="0"
                value={widMm}
                onChange={(e) => setWidMm(e.target.value)}
                className="w-16 rounded border border-h-line px-1 font-mono"
              />
            </label>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">Paint</span>
              <select
                value={paint}
                onChange={(e) => setPaint(e.target.value as PickerPayload["paint_instruction"])}
                className="rounded border border-h-line px-1 py-0.5"
              >
                <option value="NONE">None</option>
                <option value="SINGLE_SIDE">Single side</option>
                <option value="DOUBLE_SIDE">Double side</option>
                <option value="EDGE_ONLY">Edge only</option>
              </select>
            </label>
          </>
        ) : null}
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Comment (optional)"
          className="flex-1 min-w-[120px] rounded border border-h-line px-2 py-1"
        />
      </div>

      <div className="max-h-64 overflow-y-auto rounded border border-h-line bg-white">
        {filtered.length === 0 ? (
          <div className="p-3 text-h-muted">
            {rows.length === 0 ? (
              <>
                No {KIND_LABEL[kind].toLowerCase()} rows.{" "}
                <Link href={`/catalog?tab=${KIND_SLUG[kind]}`} className="text-h-accent underline">
                  Add some in Catalog
                </Link>
                .
              </>
            ) : (
              "No matches for search."
            )}
          </div>
        ) : (
          <ul className="divide-y divide-h-line">
            {filtered.map((row) => (
              <li key={row.material_id}>
                <button
                  type="button"
                  onClick={() => pick(row.material_id)}
                  className="block w-full px-2 py-1 text-left hover:bg-gray-100"
                  data-testid={`picker-pick-${row.material_id}`}
                >
                  <span className="font-mono">{row.sku}</span> — {row.description}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function LabourEditor({
  line, onSet, onClose,
}: {
  line: Line;
  onSet: (stage: StageKey, hours: number) => Promise<void>;
  onClose: () => void;
}) {
  const byStage = new Map(line.labour.map((l) => [l.stage_key, l.hours]));

  return (
    <div className="mt-2 grid grid-cols-2 gap-2 rounded border border-h-line bg-white p-3 text-xs md:grid-cols-5">
      <div className="col-span-full flex items-center justify-between">
        <span className="font-semibold">Labour hours per stage</span>
        <button type="button" onClick={onClose} className="text-h-muted hover:text-h-ink">×</button>
      </div>
      {STAGE_KEYS.map((sk) => (
        <label key={sk} className="flex flex-col">
          <span className="text-h-muted">{sk}</span>
          <input
            type="number"
            min={0}
            step="0.25"
            defaultValue={byStage.get(sk) ?? "0"}
            onBlur={(e) => onSet(sk, Number(e.target.value || 0))}
            className="mt-1 rounded border border-h-line px-1 py-0.5 font-mono"
            data-testid={`labour-${line.line_id}-${sk}`}
          />
        </label>
      ))}
    </div>
  );
}

interface RevisionRailProps {
  revisions: EstimateDetail["revisions"];
  currentId: number | null;
  selectedId: number | null;
  onSelect: (rid: number | null) => void;
}

function RevisionRail({ revisions, currentId, selectedId, onSelect }: RevisionRailProps) {
  const sorted = [...revisions].sort((a, b) => b.rev_no - a.rev_no);
  return (
    <div
      className="flex flex-wrap gap-2 rounded border border-h-line bg-h-surface p-2 text-xs"
      data-testid="revision-rail"
    >
      <span className="text-h-muted uppercase tracking-wide self-center">Revisions</span>
      {sorted.map((r) => {
        const isCurrent = r.revision_id === currentId;
        const isSelected = r.revision_id === selectedId;
        return (
          <button
            key={r.revision_id}
            type="button"
            onClick={() => onSelect(isCurrent ? null : r.revision_id)}
            className={`rounded border px-2 py-1 ${
              isSelected
                ? "border-h-accent bg-white shadow"
                : "border-h-line bg-white hover:bg-gray-50"
            }`}
            data-testid={`revision-rail-${r.rev_no}`}
          >
            <span className="font-mono">v{r.rev_no}</span>{" "}
            <span
              className={`ml-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ${STATUS_COLOURS[r.status]}`}
            >
              {r.status}
            </span>
            {isCurrent ? (
              <span className="ml-1 text-[10px] text-h-muted">current</span>
            ) : null}
            <span className="ml-2 font-mono text-h-muted">{fmtMoney(r.total_inc_gst)}</span>
          </button>
        );
      })}
    </div>
  );
}
