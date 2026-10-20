"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * Undo for delete and archive: `const { defer } = useUndo()`, then
 * `defer({ message: "Archived the row", run: () => archiveRow(...) })`.
 * Nothing is sent when the toast opens: `run` fires when the 10 seconds end, and Undo cancels it,
 * so there is no reverse API to keep in step (items restore is manager-only, archives have none).
 * A pending action is flushed at once when the tab is closed or the app shell unmounts, so leaving
 * the page never silently drops it. A request that may run then must send `keepalive: true`, or the
 * browser cancels it as the page unloads.
 */

export const UNDO_MS = 10_000;

export interface DeferOptions {
  /** Shown in the toast, in the past tense ("Archived the customer"). */
  message: string;
  /** The real request. Runs when the time is up, or early when the page is left. */
  run: () => void | Promise<void>;
  /** Called once the action is over: after `run` finished or failed, or after Undo. Re-enable the button here. */
  onSettle?: () => void;
}

interface Entry extends DeferOptions {
  id: number;
  timer: ReturnType<typeof setTimeout>;
}

interface Shown {
  id: number;
  message: string;
  /** A failed action: no Undo, click to dismiss. */
  failed?: boolean;
}

const Ctx = createContext<{ defer: (opts: DeferOptions) => void } | null>(null);

export function useUndo() {
  const api = useContext(Ctx);
  if (!api) throw new Error("useUndo needs an <UndoProvider> above it");
  return api;
}

export function UndoProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<Shown[]>([]);
  const live = useRef(new Map<number, Entry>());
  const nextId = useRef(1);

  const fire = useCallback((id: number) => {
    const e = live.current.get(id);
    if (!e) return;
    clearTimeout(e.timer);
    live.current.delete(id);
    setEntries((cur) => cur.filter((x) => x.id !== id));
    void (async () => {
      try {
        await e.run();
      } catch (err) {
        // The request fires after the user has moved on, so a failure needs its own notice.
        const failId = nextId.current++;
        setEntries((cur) => [...cur, { id: failId, message: `Failed: ${e.message} (${String(err)})`, failed: true }]);
      } finally {
        e.onSettle?.();
      }
    })();
  }, []);

  const undo = useCallback((id: number) => {
    const e = live.current.get(id);
    if (!e) return;
    clearTimeout(e.timer);
    live.current.delete(id);
    setEntries((cur) => cur.filter((x) => x.id !== id));
    e.onSettle?.();
  }, []);

  const dismiss = useCallback((id: number) => setEntries((cur) => cur.filter((x) => x.id !== id)), []);

  const defer = useCallback(
    (opts: DeferOptions) => {
      const id = nextId.current++;
      const timer = setTimeout(() => fire(id), UNDO_MS);
      live.current.set(id, { ...opts, id, timer });
      setEntries((cur) => [...cur, { id, message: opts.message }]);
    },
    [fire],
  );

  useEffect(() => {
    const map = live.current;
    const flush = () => Array.from(map.keys()).forEach(fire);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [fire]);

  const api = useMemo(() => ({ defer }), [defer]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 left-4 z-50 grid gap-2"
        role="status"
        aria-live="polite"
      >
        {entries.map((e) => (
          <div
            key={e.id}
            data-testid="undo-toast"
            className="pointer-events-auto flex items-center gap-3 rounded border border-h-line bg-h-ink px-3 py-2 text-sm text-white shadow-lg"
          >
            <span>{e.message}</span>
            {e.failed ? (
              <button type="button" onClick={() => dismiss(e.id)} className="px-2 py-0.5 font-semibold">
                Dismiss
              </button>
            ) : (
              <button
                type="button"
                data-testid="undo-toast-undo"
                onClick={() => undo(e.id)}
                className="rounded border border-white/40 px-2 py-0.5 font-semibold hover:bg-white/10"
              >
                Undo
              </button>
            )}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
