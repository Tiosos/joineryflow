"use client";

import { useCallback, useEffect, useState } from "react";

import { CommentBadge } from "@/components/comments/CommentBadge";
import { CommentThread } from "@/components/comments/CommentThread";
import type { Mentionable } from "@/lib/comments-types";
import { can } from "@/lib/permissions";
import type { Me } from "@/lib/session";
import { getDrawing, getHistory, patchDrawing } from "@/lib/shop-drawings-fetch";
import type { DrawingDetail, DrawingType, HistoryEvent, Revision } from "@/lib/shop-drawings-types";

import QueueChip from "./QueueChip";
import { fmtDate } from "./RegisterTable";
import ReviewActions from "./ReviewActions";
import StatusPill from "./StatusPill";

interface Props {
  drawingId: number;
  initialRevId: number | null;
  /** Open the selected revision's comment thread on arrival — a notification
   *  for a revision comment links here with `?comments=1`. */
  commentsOpen: boolean;
  me: Me;
  roster: Mentionable[];
  onClose: () => void;
  onChanged: () => void;
  onSelectRevision: (revId: number) => void;
  onView: (revId: number) => void;
}

type Tab = "revisions" | "notes" | "attachments" | "status" | "audit";
const TABS: { key: Tab; label: string }[] = [
  { key: "revisions", label: "Revisions" },
  { key: "notes", label: "Notes" },
  { key: "attachments", label: "Attachments" },
  { key: "status", label: "Status History" },
  { key: "audit", label: "Audit Log" },
];

/** Same rule the API applies to PATCH /shop-drawings/{id}: the drawing's
 *  creator or a manager/admin. The API decides; this only hides the inputs. */
export function canEditDetails(me: Me, d: { created_by: number; archived_at: string | null }): boolean {
  if (d.archived_at || !can(me, "shop_dwgs", "write")) return false;
  return d.created_by === me.id || me.auth_role === "manager" || me.auth_role === "admin";
}

export function queueOfDetail(d: DrawingDetail): string {
  if (d.archived_at) return "archive";
  const latest = d.revisions[0]; // newest first
  switch (latest?.status) {
    case "draft": return "being_drawn";
    case "pending": return "internal_review";
    case "rejected": return "update_required";
    default: return "completed";
  }
}

const EVENT_LABEL: Record<string, string> = {
  "shop_drawing.create": "Drawing created",
  "shop_drawing.update": "Details updated",
  "shop_drawing.archive": "Archived",
  "shop_drawing.revision.upload": "Revision uploaded",
  "shop_drawing.revision.submit": "Submitted for review",
  "shop_drawing.revision.withdraw": "Withdrawn",
  "shop_drawing.revision.approve": "Approved",
  "shop_drawing.revision.reject": "Rejected",
};

const isStatusEvent = (e: HistoryEvent) =>
  e.event === "shop_drawing.create" || e.event === "shop_drawing.archive" || e.event.startsWith("shop_drawing.revision.");

function fmtTs(iso: string): string {
  const d = new Date(iso);
  return `${fmtDate(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`)} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function DetailsPanel(props: Props) {
  const { me } = props;
  const [detail, setDetail] = useState<DrawingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRevId, setSelectedRevId] = useState<number>(props.initialRevId ?? 0);
  const [commentsOpen, setCommentsOpen] = useState(props.commentsOpen);
  const [tab, setTab] = useState<Tab>("revisions");
  const [history, setHistory] = useState<HistoryEvent[] | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  // The URL named a revision (a notification followed while this panel is
  // already open, back/forward): follow it.
  useEffect(() => { if (props.initialRevId) setSelectedRevId(props.initialRevId); }, [props.initialRevId]);
  useEffect(() => { if (props.commentsOpen) setCommentsOpen(true); }, [props.commentsOpen, props.initialRevId]);

  const refresh = useCallback(async () => {
    try {
      setDetail(await getDrawing(props.drawingId));
      setError(null);
      setHistory(null); // stale after any change; reloaded when its tab is showing
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [props.drawingId]);

  useEffect(() => { setDetail(null); setSaveErr(null); refresh(); }, [refresh]);

  // Snap the selection to a real revision once the detail loads.
  useEffect(() => {
    if (!detail) return;
    if (selectedRevId && detail.revisions.some((r) => r.revision_id === selectedRevId)) return;
    const fallback = detail.revisions[0]?.revision_id ?? 0;
    if (fallback) setSelectedRevId(fallback);
  }, [detail, selectedRevId]);

  useEffect(() => {
    if ((tab !== "status" && tab !== "audit") || history) return;
    let live = true;
    getHistory(props.drawingId).then((h) => { if (live) setHistory(h); }).catch(() => { if (live) setHistory([]); });
    return () => { live = false; };
  }, [tab, history, props.drawingId]);

  const selectedRev = detail?.revisions.find((r) => r.revision_id === selectedRevId);
  const editable = detail ? canEditDetails(me, detail) : false;

  const save = async (patch: Parameters<typeof patchDrawing>[1]) => {
    setSaveErr(null);
    try {
      setDetail(await patchDrawing(props.drawingId, patch));
      setHistory(null);
      props.onChanged();
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
      await refresh(); // put the inputs back to what the server holds
    }
  };

  return (
    <aside
      data-testid="details-panel"
      className="w-full shrink-0 overflow-hidden rounded border border-h-line bg-h-surface lg:sticky lg:top-2 lg:max-h-[calc(100vh-1rem)] lg:w-[420px] lg:self-start lg:overflow-y-auto"
    >
      <header className="flex items-start justify-between gap-3 border-b border-h-line p-4">
        <div className="min-w-0">
          <p className="h-mono text-xs text-h-muted">
            {detail?.drawing_no ?? "—"} · #SD-{String(props.drawingId).padStart(4, "0")} · {detail?.project_code ?? "…"}
          </p>
          <h2 className="truncate text-lg font-semibold text-h-ink">{detail?.title ?? "Loading…"}</h2>
        </div>
        <div className="flex items-center gap-2">
          {detail && <QueueChip queue={queueOfDetail(detail)} />}
          <button onClick={props.onClose} aria-label="Close details"
                  className="rounded p-1 text-h-muted hover:bg-h-line/40 hover:text-h-ink">✕</button>
        </div>
      </header>

      {error && <p className="p-4 text-sm text-h-bad">{error}</p>}

      {detail && (
        <>
          <section className="space-y-3 border-b border-h-line p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-h-accent">Current shop drawing details</h3>
            <Field label="Description">
              <TextInput value={detail.title} disabled={!editable} required
                         onCommit={(v) => save({ title: v ?? undefined })} />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Type">
                <select value={detail.type} disabled={!editable}
                        onChange={(e) => save({ type: e.target.value as DrawingType })}
                        className={inputCls}>
                  <option value="IFA">IFA</option>
                  <option value="IFC">IFC</option>
                </select>
              </Field>
              <Field label="Revision">
                <p className="h-mono py-1.5 text-sm text-h-ink">v{detail.revisions[0]?.rev_no ?? "—"}</p>
              </Field>
              <Field label="Submitted">
                <DateInput value={detail.submitted_at} disabled={!editable}
                           onCommit={(v) => save({ submitted_at: v })} label="Submitted date" />
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Zone"><TextInput value={detail.zone} disabled={!editable} onCommit={(v) => save({ zone: v })} /></Field>
              <Field label="Level"><TextInput value={detail.level} disabled={!editable} onCommit={(v) => save({ level: v })} /></Field>
              <Field label="Room no."><TextInput value={detail.room_no} disabled={!editable} onCommit={(v) => save({ room_no: v })} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Room"><TextInput value={detail.room} disabled={!editable} onCommit={(v) => save({ room: v })} /></Field>
              <Field label="Joinery ID"><TextInput value={detail.joinery_id} disabled={!editable} onCommit={(v) => save({ joinery_id: v })} /></Field>
            </div>
            {saveErr && <p role="alert" className="text-xs text-h-bad">{saveErr}</p>}
            {!editable && !detail.archived_at && (
              <p className="text-xs text-h-muted">Only the drawing&apos;s creator or a manager can edit these details.</p>
            )}
          </section>

          <section className="space-y-3 border-b border-h-line p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-h-ink2">Drafter information</h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Assigned to">
                <select
                  value={detail.assigned_to ?? ""}
                  disabled={!editable}
                  onChange={(e) => save({ assigned_to: e.target.value ? Number(e.target.value) : null })}
                  className={inputCls}
                >
                  <option value="">Unassigned</option>
                  {/* The assignee may not be on the roster (deactivated): keep them selectable so the value shows. */}
                  {detail.assigned_to != null && !props.roster.some((m) => m.id === detail.assigned_to) && (
                    <option value={detail.assigned_to}>{detail.assigned_to_name ?? `User ${detail.assigned_to}`}</option>
                  )}
                  {props.roster.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                </select>
              </Field>
              <Field label="Due date">
                <DateInput value={detail.due_date} disabled={!editable}
                           onCommit={(v) => save({ due_date: v })} label="Due date" />
              </Field>
            </div>
          </section>

          <section className="border-b border-h-line">
            <h3 className="px-4 pt-3 text-[11px] font-semibold uppercase tracking-wider text-h-ink2">Revision details</h3>
            <div role="tablist" className="flex gap-1 overflow-x-auto px-3 pt-2">
              {TABS.map((t) => (
                <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                        className={`whitespace-nowrap rounded-t px-2.5 py-1.5 text-xs ${
                          tab === t.key ? "border-b-2 border-h-accent font-medium text-h-ink" : "text-h-muted hover:text-h-ink"
                        }`}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="border-t border-h-line">
              {tab === "revisions" && (
                <RevisionList revisions={detail.revisions} selectedId={selectedRevId}
                              onSelect={(id) => { setSelectedRevId(id); props.onSelectRevision(id); }}
                              onView={props.onView} />
              )}
              {tab === "notes" && <Notes revisions={detail.revisions} />}
              {tab === "attachments" && <Attachments revisions={detail.revisions} />}
              {tab === "status" && <EventList events={history?.filter(isStatusEvent) ?? null} />}
              {tab === "audit" && <EventList events={history} />}
            </div>
          </section>

          {selectedRev && (
            <section data-testid="revision-comments" className="border-b border-h-line">
              <button type="button" onClick={() => setCommentsOpen((o) => !o)} aria-expanded={commentsOpen}
                      className="flex w-full items-center justify-between px-4 py-2 text-left text-sm font-medium text-h-ink hover:bg-h-surface-alt">
                <span>Comments on v{selectedRev.rev_no}</span>
                <span aria-hidden className="text-h-muted">{commentsOpen ? "▾" : "▸"}</span>
              </button>
              {commentsOpen && (
                <div className="max-h-72 overflow-y-auto border-t border-h-line p-3">
                  <CommentThread
                    key={selectedRev.revision_id}
                    objectType="revision"
                    objectId={selectedRev.revision_id}
                    currentUserId={me.id}
                    currentUserRole={me.auth_role}
                    canComment={can(me, "shop_dwgs", "comment")}
                    onMutated={() => { void refresh(); props.onChanged(); }}
                    roster={props.roster}
                  />
                </div>
              )}
            </section>
          )}

          {selectedRev && (
            <footer className="flex flex-wrap items-center gap-2 p-4">
              <ReviewActions
                detail={detail}
                selectedRev={selectedRev}
                me={me}
                onAfter={async () => { await refresh(); props.onChanged(); }}
              />
            </footer>
          )}
        </>
      )}
    </aside>
  );
}

const inputCls =
  "block w-full rounded-md border border-h-line bg-h-surface px-2 py-1.5 text-sm text-h-ink disabled:bg-h-surface-alt disabled:text-h-ink2 focus:outline-none focus:ring-2 focus:ring-h-accent";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[11px] text-h-muted">{label}</span>
      {children}
    </label>
  );
}

/** Commit-on-blur text input that resyncs when the server value changes, and
 *  never sends an unchanged value (a bare tab-through would otherwise write an
 *  audit row per field). Empty clears a nullable field; `required` refuses it. */
function TextInput({ value, disabled, required, onCommit }: {
  value: string | null; disabled: boolean; required?: boolean; onCommit: (v: string | null) => void;
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  const commit = () => {
    const next = v.trim();
    if (next === (value ?? "")) { setV(value ?? ""); return; }
    if (required && !next) { setV(value ?? ""); return; }
    onCommit(next === "" ? null : next);
  };
  return (
    <input value={v} disabled={disabled} onChange={(e) => setV(e.target.value)} onBlur={commit}
           onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
           className={inputCls} />
  );
}

function DateInput({ value, disabled, onCommit, label }: {
  value: string | null; disabled: boolean; onCommit: (v: string | null) => void; label: string;
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  // Saves on blur, not change: a native date input fires onChange with "" while a
  // date is being typed, which would wipe an existing date on the first keystroke.
  const commit = () => { if (v !== (value ?? "")) onCommit(v || null); };
  return (
    <input type="date" aria-label={label} value={v} disabled={disabled}
           onChange={(e) => setV(e.target.value)} onBlur={commit} className={inputCls} />
  );
}

function RevisionList({ revisions, selectedId, onSelect, onView }: {
  revisions: Revision[]; selectedId: number; onSelect: (id: number) => void; onView: (id: number) => void;
}) {
  return (
    <ol className="divide-y divide-h-line">
      {revisions.map((r, i) => (
        <li key={r.revision_id} className={r.revision_id === selectedId ? "bg-h-accent-soft/50" : ""}>
          <div className="flex items-center gap-2 px-4 py-2 text-sm">
            <button type="button" onClick={() => onSelect(r.revision_id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
              <span className="h-mono font-medium text-h-ink">v{r.rev_no}</span>
              <StatusPill status={r.status} />
              {i === 0 && <span className="rounded bg-h-good/15 px-1.5 text-[10px] font-semibold uppercase text-h-good">Latest</span>}
              <span className="min-w-0 flex-1 truncate text-xs text-h-muted">{r.uploaded_by_name ?? "—"}</span>
              <span className="h-mono text-xs text-h-muted">{fmtTs(r.uploaded_at).slice(0, -6)}</span>
              <CommentBadge n={r.comment_count} />
            </button>
            <button type="button" onClick={() => onView(r.revision_id)} aria-label={`View v${r.rev_no}`}
                    className="rounded border border-h-line px-2 py-0.5 text-xs text-h-accent hover:bg-h-surface-alt">View</button>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Notes({ revisions }: { revisions: Revision[] }) {
  const noted = revisions.filter((r) => r.review_note);
  if (noted.length === 0) return <p className="p-4 text-sm text-h-muted">No review notes yet.</p>;
  return (
    <ul className="divide-y divide-h-line">
      {noted.map((r) => (
        <li key={r.revision_id} className="space-y-0.5 px-4 py-2 text-sm">
          <p className="text-xs text-h-muted">
            v{r.rev_no} · {r.reviewed_by_name ?? "Reviewer"}{r.reviewed_at ? ` · ${fmtTs(r.reviewed_at)}` : ""}
          </p>
          <p className="text-h-ink">{r.review_note}</p>
        </li>
      ))}
    </ul>
  );
}

function Attachments({ revisions }: { revisions: Revision[] }) {
  return (
    <ul className="divide-y divide-h-line">
      {revisions.map((r) => (
        <li key={r.revision_id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
          <span className="text-h-ink">v{r.rev_no} <span className="text-xs text-h-muted">· {r.file_mime.split("/")[1]?.toUpperCase()}</span></span>
          <span className="flex gap-3 text-xs">
            <a href={`/api/files/${r.file_blob_id}`} target="_blank" rel="noreferrer" className="text-h-accent hover:underline">Open</a>
            <a href={`/api/files/${r.file_blob_id}`} download className="text-h-accent hover:underline">Download</a>
          </span>
        </li>
      ))}
    </ul>
  );
}

function EventList({ events }: { events: HistoryEvent[] | null }) {
  if (events === null) return <p className="p-4 text-sm text-h-muted">Loading…</p>;
  if (events.length === 0) return <p className="p-4 text-sm text-h-muted">Nothing recorded yet.</p>;
  return (
    <ul className="divide-y divide-h-line">
      {events.map((e, i) => {
        const p = e.payload as Record<string, unknown>;
        const detail =
          e.event === "shop_drawing.update" ? `${String(p.field)} → ${p.value == null || p.value === "" ? "cleared" : String(p.value)}` :
          typeof p.rev_no === "number" ? `v${p.rev_no}` : "";
        const note = typeof p.review_note === "string" && p.review_note ? p.review_note : null;
        return (
          <li key={i} className="px-4 py-2 text-sm">
            <p className="text-h-ink">
              {EVENT_LABEL[e.event] ?? e.event}
              {detail && <span className="text-h-muted"> · {detail}</span>}
            </p>
            {note && <p className="text-xs text-h-muted">“{note}”</p>}
            <p className="text-xs text-h-muted">{e.actor_name ?? "System"} · {fmtTs(e.created_at)}</p>
          </li>
        );
      })}
    </ul>
  );
}
