"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ActualCosts, ProjectContract } from "@/lib/project-contract-types";
import { projectContractApi } from "@/lib/project-contract-fetch";

interface Props {
  projectId: number;
  /** null when this project wasn't created from a converted estimate (Q491) — no contract row exists yet. */
  contract: ProjectContract | null;
  actualCosts: ActualCosts;
  /** tracking:write — {editor, drafter, manager, admin}. */
  canEdit: boolean;
}

function fmtMoney(s: string | null | undefined): string {
  if (s == null) return "—";
  const n = parseFloat(s);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function ProjectFinancialsCard({ projectId, contract, actualCosts, canEdit }: Props) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-h-ink">Financials</h2>
        {canEdit && contract && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-h-accent hover:underline"
          >
            + Add variation
          </button>
        )}
      </div>

      {contract ? (
        <>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                Contract Value (original)
              </div>
              <div className="mt-0.5 font-mono tabular-nums text-h-ink">
                {fmtMoney(contract.original_value)}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                Contract Value (current)
              </div>
              <div className="mt-0.5 font-mono tabular-nums text-h-ink">
                {fmtMoney(contract.current_value)}
              </div>
            </div>
          </div>

          {adding && (
            <AddVariationForm
              projectId={projectId}
              onDone={() => {
                setAdding(false);
                router.refresh();
              }}
              onCancel={() => setAdding(false)}
            />
          )}

          {contract.variations.length > 0 && (
            <ul className="mt-3 grid gap-1 text-xs text-h-muted">
              {contract.variations.map((v) => (
                <li key={v.variation_id} className="flex justify-between gap-2">
                  <span>{v.description}</span>
                  <span className="font-mono">{fmtMoney(v.amount_delta)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="text-sm text-h-muted">No contract on this project yet.</p>
      )}

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-h-line pt-3 text-sm">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
            Materials (actual)
          </div>
          <div className="mt-0.5 font-mono tabular-nums text-h-ink">
            {fmtMoney(actualCosts.materials_actual)}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
            Labour (actual)
          </div>
          <div className="mt-0.5 font-mono tabular-nums text-h-ink">
            {fmtMoney(actualCosts.labour_actual)}
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
            Total (actual)
          </div>
          <div className="mt-0.5 font-mono tabular-nums text-h-ink">
            {fmtMoney(actualCosts.total_actual)}
          </div>
        </div>
      </div>
      <p className="mt-2 text-xs italic text-h-muted">
        Actual costs are derived from received procurement and completed
        production stages (Q493) — nothing here is entered by hand.
      </p>
    </section>
  );
}

function AddVariationForm({
  projectId,
  onDone,
  onCancel,
}: {
  projectId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [description, setDescription] = useState("");
  const [amountDelta, setAmountDelta] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!description.trim() || !amountDelta.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await projectContractApi.addVariation(projectId, description.trim(), amountDelta.trim());
      onDone();
    } catch {
      setError("Failed to add variation");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 grid gap-2 rounded border border-h-line bg-h-bg p-2">
      <div className="flex flex-wrap gap-2">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description *"
          className="min-w-40 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
        <input
          value={amountDelta}
          onChange={(e) => setAmountDelta(e.target.value)}
          placeholder="Amount (+/-) *"
          className="w-32 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
      </div>
      {error && <p className="text-xs text-rose-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !description.trim() || !amountDelta.trim()}
          className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          Add
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
