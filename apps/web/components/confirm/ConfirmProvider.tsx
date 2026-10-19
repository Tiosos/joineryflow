"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * The one confirmation dialog for risky actions (delete, archive, cancel, reject, close out):
 * `const { confirm, askReason } = useConfirm()`, then `if (!(await confirm({ ... }))) return;`.
 * It replaces `window.confirm` / `window.prompt` for those actions: the same words, but a real
 * dialog (focus moves in and back, Esc and Tab behave, the destructive button is named and styled).
 * One dialog at a time; asking while one is open cancels the first.
 */

export interface ConfirmOptions {
  title: string;
  /** What will happen, in plain words (the old `window.confirm` text goes here). */
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** `danger` (default) styles the confirm button as destructive and focuses Cancel first. */
  tone?: "danger" | "default";
}

export interface ReasonOptions extends ConfirmOptions {
  reasonLabel?: string;
  /** Default true: Confirm stays disabled until a reason is typed. */
  reasonRequired?: boolean;
}

type Pending =
  | { kind: "confirm"; opts: ConfirmOptions; resolve: (ok: boolean) => void }
  | { kind: "reason"; opts: ReasonOptions; resolve: (reason: string | null) => void };

interface Api {
  /** Resolves true when confirmed, false when cancelled (Cancel, Esc, backdrop). */
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
  /** Resolves the typed reason (trimmed; "" when optional and left empty), or null when cancelled. */
  askReason: (opts: ReasonOptions) => Promise<string | null>;
}

const Ctx = createContext<Api | null>(null);

export function useConfirm(): Api {
  const api = useContext(Ctx);
  if (!api) throw new Error("useConfirm needs a <ConfirmProvider> above it");
  return api;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  pendingRef.current = pending;

  const open = useCallback((next: Pending) => {
    // A second request while one is open cancels the first.
    const cur = pendingRef.current;
    if (cur) (cur.resolve as (v: boolean | null) => void)(cur.kind === "confirm" ? false : null);
    setPending(next);
  }, []);

  const api = useMemo<Api>(
    () => ({
      confirm: (opts) => new Promise<boolean>((resolve) => open({ kind: "confirm", opts, resolve })),
      askReason: (opts) => new Promise<string | null>((resolve) => open({ kind: "reason", opts, resolve })),
    }),
    [open],
  );

  const settle = useCallback((value: boolean | string | null) => {
    const cur = pendingRef.current;
    if (!cur) return;
    setPending(null);
    if (cur.kind === "confirm") cur.resolve(value === true);
    else cur.resolve(typeof value === "string" ? value : null);
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      {pending && <ConfirmDialog key={pending.opts.title + pending.kind} pending={pending} onSettle={settle} />}
    </Ctx.Provider>
  );
}

function ConfirmDialog({
  pending,
  onSettle,
}: {
  pending: Pending;
  onSettle: (value: boolean | string | null) => void;
}) {
  const { opts } = pending;
  const isReason = pending.kind === "reason";
  const reasonRequired = isReason && (pending.opts.reasonRequired ?? true);
  const danger = (opts.tone ?? "danger") === "danger";
  const titleId = useId();
  const bodyId = useId();
  const [reason, setReason] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const canConfirm = !reasonRequired || reason.trim() !== "";

  const cancel = useCallback(() => onSettle(isReason ? null : false), [isReason, onSettle]);
  const confirm = useCallback(() => {
    if (!canConfirm) return;
    onSettle(isReason ? reason.trim() : true);
  }, [canConfirm, isReason, onSettle, reason]);

  // Focus goes in on open and back to where it was on close.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    (isReason ? reasonRef : danger ? cancelRef : confirmRef).current?.focus();
    return () => before?.focus?.();
  }, [isReason, danger]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      cancel();
    } else if (e.key === "Tab") {
      // Keep Tab inside the dialog.
      const items = boxRef.current?.querySelectorAll<HTMLElement>("textarea, button:not([disabled])");
      if (!items || items.length === 0) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) cancel(); }}
    >
      <div
        ref={boxRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={opts.message ? bodyId : undefined}
        data-testid="confirm-dialog"
        onKeyDown={onKeyDown}
        className="w-full max-w-md rounded-lg border border-h-line bg-h-surface p-4 text-h-ink shadow-lg"
      >
        <h2 id={titleId} className="text-base font-semibold">{opts.title}</h2>
        {opts.message && (
          <div id={bodyId} data-testid="confirm-dialog-message" className="mt-2 text-sm text-h-muted">
            {opts.message}
          </div>
        )}
        {isReason && (
          <label className="mt-3 block text-sm">
            <span className="text-h-muted">
              {pending.opts.reasonLabel ?? "Reason"}{reasonRequired ? "" : " (optional)"}
            </span>
            <textarea
              ref={reasonRef}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              data-testid="confirm-dialog-reason"
              className="mt-1 w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
            />
          </label>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            data-testid="confirm-dialog-cancel"
            onClick={cancel}
            className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
          >
            {opts.cancelLabel ?? "Cancel"}
          </button>
          <button
            ref={confirmRef}
            type="button"
            data-testid="confirm-dialog-confirm"
            disabled={!canConfirm}
            onClick={confirm}
            className={[
              "rounded px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50",
              danger ? "bg-h-bad hover:opacity-90" : "bg-h-accent hover:opacity-90",
            ].join(" ")}
          >
            {opts.confirmLabel ?? (danger ? "Delete" : "Confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
