"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import type { Me } from "@/lib/session";
import type { EstimateDetail, GenerateOrdersResult, Line, OrderPreview } from "@/lib/estimating-types";
import { nextStageLabel, CatalogMap, STATUS_COLOURS, fmtMoney, summariseGenerateResult, CallApiFn } from "./estimate-detail/shared";
import { ConvertPreviewDialog } from "./estimate-detail/ConvertPreviewDialog";
import { OrderPreviewDialog } from "./estimate-detail/OrderPreviewDialog";
import { SummaryCard } from "./estimate-detail/SummaryCard";
import { NewLineForm } from "./estimate-detail/NewLineForm";
import { DraggableLineList } from "./estimate-detail/DraggableLineList";
import { RevisionRail } from "./estimate-detail/RevisionRail";

interface Props {
  me: Me;
  estimate: EstimateDetail;
  catalogs: CatalogMap;
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
