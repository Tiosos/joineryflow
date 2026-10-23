"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { ActualCosts, ProjectContract } from "@/lib/project-contract-types";
import { projectContractApi } from "@/lib/project-contract-fetch";
import { useConfirm } from "@/components/confirm/ConfirmProvider";
import { useUndo } from "@/components/undo/UndoProvider";
import type { ContractVariation, VariationItem } from "@/lib/project-contract-types";

interface Props {
  projectId: number;
  /** null when this project wasn't created from a converted estimate (Q491) — no contract row exists yet. */
  contract: ProjectContract | null;
  actualCosts: ActualCosts;
  /** tracking:write — {editor, drafter, manager, admin}. */
  canEdit: boolean;
  /** Manager or admin: approves or rejects a Draft variation, and a manager's own is Approved at once (Q608). */
  canDecide: boolean;
  meId: number | null;
}

function fmtMoney(s: string | null | undefined): string {
  if (s == null) return "—";
  const n = parseFloat(s);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function ProjectFinancialsCard({ projectId, contract, actualCosts, canEdit, canDecide, meId }: Props) {
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
              approvedAtOnce={canDecide}
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
                <VariationRow
                  key={v.variation_id}
                  projectId={projectId}
                  v={v}
                  canEditThis={canEdit && (canDecide || v.created_by === meId)}
                  canDecideThis={canDecide}
                />
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
      {actualCosts.unresolved_labour_completions > 0 && (
        <p role="status" className="mt-2 text-xs text-amber-800">
          {`${actualCosts.unresolved_labour_completions} production completion(s) have unresolved labour costs. Labour and total actuals remain unavailable until their historical rate and start time are known.`}
        </p>
      )}
      <p className="mt-2 text-xs italic text-h-muted">
        Actual costs are derived from received procurement and completed
        production stages (Q493) — nothing here is entered by hand.
      </p>
    </section>
  );
}

const STATUS_STYLE: Record<ContractVariation["status"], string> = {
  Draft: "bg-amber-100 text-amber-800",
  Approved: "bg-emerald-100 text-emerald-800",
  Rejected: "bg-rose-100 text-rose-800",
  Voided: "bg-slate-200 text-slate-700",
};

function VariationRow({
  projectId,
  v,
  canEditThis,
  canDecideThis,
}: {
  projectId: number;
  v: ContractVariation;
  canEditThis: boolean;
  canDecideThis: boolean;
}) {
  const router = useRouter();
  const { confirm, askReason, askFields } = useConfirm();
  const { notify } = useUndo();
  const isDraft = v.status === "Draft";
  const [linking, setLinking] = useState(false);
  const [picked, setPicked] = useState<number[]>(v.items.map((i) => i.item_id));

  async function run(fn: () => Promise<unknown>) {
    try {
      await fn();
      router.refresh();
    } catch {
      notify("That change was not saved. Reload and try again.");
    }
  }

  async function approve() {
    if (
      !(await confirm({
        title: "Approve variation",
        message: `Approve "${v.description}" (${fmtMoney(v.amount_delta)})? It then counts toward the current contract value. A decision cannot be reopened.`,
        confirmLabel: "Approve",
        tone: "default",
      }))
    )
      return;
    await run(() => projectContractApi.decideVariation(projectId, v.variation_id, "approved"));
  }

  async function reject() {
    const note = await askReason({
      title: "Reject variation",
      message: `Reject "${v.description}"? It will never count toward the contract value. A decision cannot be reopened.`,
      reasonLabel: "Reason",
      confirmLabel: "Reject",
    });
    if (!note) return;
    await run(() => projectContractApi.decideVariation(projectId, v.variation_id, "rejected", note));
  }

  async function voidIt() {
    const reason = await askReason({
      title: "Void variation",
      message: `Void "${v.description}" (${fmtMoney(v.amount_delta)})? It stays in the list but stops counting toward the contract value. This cannot be undone.`,
      reasonLabel: "Reason",
      confirmLabel: "Void",
    });
    if (!reason) return;
    await run(() => projectContractApi.voidVariation(projectId, v.variation_id, reason));
  }

  async function edit() {
    const r = await askFields({
      title: "Edit variation",
      confirmLabel: "Save",
      tone: "default",
      fields: [
        { name: "description", label: "Description", initial: v.description, required: true },
        { name: "amount", label: "Amount (+/-)", initial: v.amount_delta, required: true },
      ],
    });
    if (!r) return;
    await run(() => projectContractApi.editVariation(projectId, v.variation_id, { description: r.description, amount_delta: r.amount }));
  }

  async function saveLinks() {
    await run(() => projectContractApi.editVariation(projectId, v.variation_id, { item_ids: picked }));
    setLinking(false);
  }

  return (
    <li data-testid="variation-row" className="grid gap-0.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className={v.status === "Rejected" || v.status === "Voided" ? "line-through" : undefined}>
          {v.description}{" "}
          <span
            data-testid="variation-status"
            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[v.status]}`}
          >
            {v.status}
          </span>
        </span>
        <span className={`font-mono ${v.status === "Approved" ? "" : "opacity-60"}`}>{fmtMoney(v.amount_delta)}</span>
      </div>
      {v.decision_note && <div className="italic">{v.decision_note}</div>}
      {v.void_reason && <div className="italic">{`Voided: ${v.void_reason}`}</div>}
      {v.status === "Approved" && canDecideThis && (
        <div className="flex gap-3">
          <button type="button" onClick={voidIt} className="text-rose-700 hover:underline">
            Void
          </button>
        </div>
      )}
      {v.items.length > 0 && (
        <div data-testid="variation-items" className="flex flex-wrap gap-1">
          {v.items.map((i) => (
            <span key={i.item_id} className="rounded border border-h-line px-1.5 py-0.5 text-[10px]">
              {`#${i.num}${i.description ? ` ${i.description}` : ""}`}
            </span>
          ))}
        </div>
      )}
      {linking && (
        <div className="grid gap-1 rounded border border-h-line bg-h-bg p-2">
          <ItemPicker projectId={projectId} selected={picked} onChange={setPicked} />
          <div className="flex gap-2">
            <button type="button" onClick={saveLinks} className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white">
              Save items
            </button>
            <button type="button" onClick={() => setLinking(false)} className="rounded border border-h-line px-2 py-1 text-xs text-h-ink">
              Cancel
            </button>
          </div>
        </div>
      )}
      {isDraft && (canEditThis || canDecideThis) && (
        <div className="flex gap-3">
          {canDecideThis && (
            <button type="button" onClick={approve} className="text-h-accent hover:underline">
              Approve
            </button>
          )}
          {canDecideThis && (
            <button type="button" onClick={reject} className="text-rose-700 hover:underline">
              Reject
            </button>
          )}
          {canEditThis && (
            <button type="button" onClick={edit} className="text-h-ink hover:underline">
              Edit
            </button>
          )}
          {canEditThis && !linking && (
            <button
              type="button"
              onClick={() => {
                setPicked(v.items.map((i) => i.item_id));
                setLinking(true);
              }}
              className="text-h-ink hover:underline"
            >
              Items
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function AddVariationForm({
  projectId,
  approvedAtOnce,
  onDone,
  onCancel,
}: {
  projectId: number;
  approvedAtOnce: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [description, setDescription] = useState("");
  const [amountDelta, setAmountDelta] = useState("");
  const [itemIds, setItemIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!description.trim() || !amountDelta.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await projectContractApi.addVariation(projectId, description.trim(), amountDelta.trim(), itemIds);
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
      <ItemPicker projectId={projectId} selected={itemIds} onChange={setItemIds} />
      <p className="text-xs text-h-muted">
        {approvedAtOnce
          ? "Approved immediately and counted in the current contract value."
          : "Added as a draft until a manager approves it; it does not count until then."}
      </p>
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

/** Optional links to the project's Joinery Items (Q609): none ticked = a project-level variation. */
function ItemPicker({
  projectId,
  selected,
  onChange,
}: {
  projectId: number;
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const [items, setItems] = useState<VariationItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    projectContractApi
      .linkableItems(projectId)
      .then((r) => live && setItems(r))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [projectId]);

  if (failed) return <p className="text-xs text-rose-700">Could not load the items.</p>;
  if (items == null) return <p className="text-xs text-h-muted">Loading items…</p>;
  if (items.length === 0) return <p className="text-xs text-h-muted">No items in this project to link.</p>;
  return (
    <fieldset data-testid="variation-item-picker" className="grid gap-1">
      <legend className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        Items touched (optional)
      </legend>
      <div className="max-h-32 overflow-auto rounded border border-h-line bg-white p-1 text-xs">
        {items.map((i) => (
          <label key={i.item_id} className="flex items-center gap-2 py-0.5">
            <input
              type="checkbox"
              checked={selected.includes(i.item_id)}
              onChange={(e) =>
                onChange(e.target.checked ? [...selected, i.item_id] : selected.filter((x) => x !== i.item_id))
              }
            />
            <span>{`#${i.num}${i.description ? ` ${i.description}` : ""}`}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
