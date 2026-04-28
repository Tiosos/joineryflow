"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

type FormState = {
  project_code: string;
  name: string;
  install_start: string; // ISO date string or empty
};

const EMPTY: FormState = { project_code: "", name: "", install_start: "" };

export function CreateProjectDrawer() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  function close() {
    setOpen(false);
    setForm(EMPTY);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const body: Record<string, unknown> = {
      project_code: form.project_code,
      name: form.name,
    };
    if (form.install_start) body.install_start = form.install_start;
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const txt = await res.text();
      setError(`Failed (${res.status}): ${txt}`);
      return;
    }
    startTransition(() => {
      router.refresh();
      close();
    });
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
      >
        + New project
      </button>

      {open && (
        <div className="fixed inset-0 z-40 bg-black/40" onClick={close}>
          <div
            className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-h-line bg-h-surface p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Create project"
          >
            <header className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-h-ink">New Project</h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="text-h-muted hover:text-h-ink"
              >
                ✕
              </button>
            </header>
            <form onSubmit={submit} className="grid gap-4">
              <label className="grid gap-1">
                <span className="text-xs font-medium uppercase text-h-muted">
                  Project Code
                </span>
                <input
                  required
                  value={form.project_code}
                  onChange={(e) =>
                    setForm({ ...form, project_code: e.target.value })
                  }
                  className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm text-h-ink"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium uppercase text-h-muted">
                  Name
                </span>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm text-h-ink"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs font-medium uppercase text-h-muted">
                  Install Start (optional)
                </span>
                <input
                  type="date"
                  value={form.install_start}
                  onChange={(e) =>
                    setForm({ ...form, install_start: e.target.value })
                  }
                  className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm text-h-ink"
                />
              </label>
              {error && (
                <p className="rounded border border-h-bad/30 bg-h-bad/10 p-2 text-xs text-h-bad">
                  {error}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={close}
                  className="rounded border border-h-line px-3 py-1.5 text-sm text-h-muted hover:text-h-ink"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {isPending ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
