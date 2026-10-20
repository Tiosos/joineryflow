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
 * `askText` / `askFields` replace `window.prompt` for names and small forms (not destructive: neutral tone).
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

export interface FieldSpec {
  name: string;
  label: string;
  initial?: string;
  /** Default false: an optional field may be left empty (the value is ""). */
  required?: boolean;
  placeholder?: string;
}

export interface FieldsOptions extends ConfirmOptions {
  fields: FieldSpec[];
}

export interface TextOptions extends ConfirmOptions {
  label: string;
  initial?: string;
  required?: boolean;
  placeholder?: string;
}

type PendingBody =
  | { kind: "confirm"; opts: ConfirmOptions; resolve: (ok: boolean) => void }
  | { kind: "reason"; opts: ReasonOptions; resolve: (reason: string | null) => void }
  | { kind: "fields"; opts: FieldsOptions; resolve: (values: Record<string, string> | null) => void };
/** `id` is new for every prompt, so a prompt that replaces another of the same title starts from scratch. */
type Pending = PendingBody & { id: number };

interface Api {
  /** Resolves true when confirmed, false when cancelled (Cancel, Esc, backdrop). */
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
  /** Resolves the typed reason (trimmed; "" when optional and left empty), or null when cancelled. */
  askReason: (opts: ReasonOptions) => Promise<string | null>;
  /** One text box. Resolves the trimmed text ("" when optional and left empty), or null when cancelled. */
  askText: (opts: TextOptions) => Promise<string | null>;
  /** Several text boxes. Resolves the trimmed values by field name, or null when cancelled. */
  askFields: (opts: FieldsOptions) => Promise<Record<string, string> | null>;
}

const Ctx = createContext<Api | null>(null);

export function useConfirm(): Api {
  const api = useContext(Ctx);
  if (!api) throw new Error("useConfirm needs a <ConfirmProvider> above it");
  return api;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  // The ref is written here, not at render: two prompts asked in the same tick must see each other.
  const pendingRef = useRef<Pending | null>(null);
  const seq = useRef(0);

  const open = useCallback((body: PendingBody) => {
    // A second request while one is open cancels the first.
    const cur = pendingRef.current;
    if (cur) (cur.resolve as (v: boolean | null) => void)(cur.kind === "confirm" ? false : null);
    const next: Pending = { ...body, id: ++seq.current };
    pendingRef.current = next;
    setPending(next);
  }, []);

  const api = useMemo<Api>(() => {
    const askFields: Api["askFields"] = (opts) =>
      new Promise((resolve) => open({ kind: "fields", opts: { tone: "default", ...opts }, resolve }));
    return {
      confirm: (opts) => new Promise<boolean>((resolve) => open({ kind: "confirm", opts, resolve })),
      askReason: (opts) => new Promise<string | null>((resolve) => open({ kind: "reason", opts, resolve })),
      askFields,
      askText: async ({ label, initial, required, placeholder, ...rest }) => {
        const v = await askFields({ ...rest, fields: [{ name: "text", label, initial, required, placeholder }] });
        return v ? v.text : null;
      },
    };
  }, [open]);

  const settle = useCallback((value: boolean | string | Record<string, string> | null) => {
    const cur = pendingRef.current;
    if (!cur) return;
    pendingRef.current = null;
    setPending(null);
    if (cur.kind === "confirm") cur.resolve(value === true);
    else if (cur.kind === "reason") cur.resolve(typeof value === "string" ? value : null);
    else cur.resolve(value !== null && typeof value === "object" ? value : null);
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      {pending && <ConfirmDialog key={pending.id} pending={pending} onSettle={settle} />}
    </Ctx.Provider>
  );
}

function ConfirmDialog({
  pending,
  onSettle,
}: {
  pending: Pending;
  onSettle: (value: boolean | string | Record<string, string> | null) => void;
}) {
  const { opts } = pending;
  const isReason = pending.kind === "reason";
  const isFields = pending.kind === "fields";
  const specs = pending.kind === "fields" ? pending.opts.fields : [];
  const reasonRequired = isReason && (pending.opts.reasonRequired ?? true);
  const danger = (opts.tone ?? "danger") === "danger";
  const titleId = useId();
  const bodyId = useId();
  const [reason, setReason] = useState("");
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(specs.map((f) => [f.name, f.initial ?? ""])),
  );
  const boxRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const fieldsRef = useRef<HTMLInputElement>(null);
  const canConfirm =
    (!reasonRequired || reason.trim() !== "") &&
    specs.every((f) => !f.required || (values[f.name] ?? "").trim() !== "");

  const cancel = useCallback(() => onSettle(isReason || isFields ? null : false), [isReason, isFields, onSettle]);
  const confirm = useCallback(() => {
    if (!canConfirm) return;
    if (isFields) onSettle(Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()])));
    else onSettle(isReason ? reason.trim() : true);
  }, [canConfirm, isReason, isFields, onSettle, reason, values]);

  // Focus goes in on open and back to where it was on close.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    (isFields ? fieldsRef : isReason ? reasonRef : danger ? cancelRef : confirmRef).current?.focus();
    fieldsRef.current?.select();
    return () => before?.focus?.();
  }, [isReason, isFields, danger]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      cancel();
    } else if (e.key === "Tab") {
      // Keep Tab inside the dialog.
      const items = boxRef.current?.querySelectorAll<HTMLElement>("textarea, input, button:not([disabled])");
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
        {isFields && (
          <div className="mt-3 grid gap-2">
            {specs.map((f, i) => (
              <label key={f.name} className="block text-sm">
                <span className="text-h-muted">{f.label}{f.required ? "" : " (optional)"}</span>
                <input
                  ref={i === 0 ? fieldsRef : undefined}
                  value={values[f.name] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => setValues((cur) => ({ ...cur, [f.name]: e.target.value }))}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); confirm(); } }}
                  data-testid={`confirm-dialog-field-${f.name}`}
                  className="mt-1 w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
                />
              </label>
            ))}
          </div>
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
