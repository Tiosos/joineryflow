"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { listSamples } from "@/lib/samples-fetch";
import type { SampleListResp, SampleStatus } from "@/lib/samples-types";

import SampleFilters from "./SampleFilters";
import SubtabStrip from "./SubtabStrip";

interface Project { id: number; project_code: string; name: string; }
interface Me { id: number; auth_role: string; full_name: string; workspace_id: number; }

interface Props {
  me: Me;
  projects: Project[];
  initialProjectId: number | null;
  initialSubtab: "board" | "ledger" | "archive";
  initialQ: string | null;
  initialStatus: string | null;
  initialSupplier: string | null;
  initialSampleId: number | null;
  initialNewOpen: boolean;
}

export default function ISampleClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const [list, setList] = useState<SampleListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const projectId = props.initialProjectId;
  const subtab = props.initialSubtab;
  const q = props.initialQ;
  const status = (props.initialStatus as SampleStatus | null) ?? null;
  const supplier = props.initialSupplier;

  useEffect(() => {
    if (projectId == null || subtab === "ledger") { setList(null); return; }
    setLoading(true);
    setError(null);
    listSamples({
      projectId, subtab: subtab as "board" | "archive",
      q, status, supplier,
    })
      .then(setList)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, subtab, q, status, supplier]);

  const updateUrl = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === "") next.delete(k); else next.set(k, v);
    }
    router.replace(`/isample?${next.toString()}`);
  }, [router, sp]);

  const suppliers = useMemo(() => {
    const seen = new Set<string>();
    for (const s of list?.samples ?? []) if (s.supplier) seen.add(s.supplier);
    return Array.from(seen).sort();
  }, [list]);

  const counts = list?.counts ?? { pending: 0, approved: 0, rejected: 0 };
  const headerText = projectId
    ? `${list?.total ?? 0} samples · ${counts.pending} awaiting client · ${counts.approved} approved · ${counts.rejected} rejected`
    : "Pick a project to view samples.";

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">iSample</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {/* "+ New sample" button mounted in Task 10 */}
      </header>

      <SampleFilters
        projects={props.projects}
        selectedProjectId={projectId}
        selectedStatus={status}
        selectedSupplier={supplier}
        searchValue={q ?? ""}
        suppliers={suppliers}
        counts={counts}
        onProjectChange={(id) => updateUrl({ project: String(id), sample: null })}
        onStatusChange={(s) => updateUrl({ status: s })}
        onSupplierChange={(s) => updateUrl({ supplier: s })}
        onSearchChange={(s) => updateUrl({ q: s || null })}
      />

      <SubtabStrip
        current={subtab}
        onChange={(s) => updateUrl({ subtab: s, sample: null })}
        pendingCount={counts.pending}
      />

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-rose-700">{error}</p>}

      {/* SampleCard grid mounted in Task 8; ApprovalLedger in Task 11 */}
      {subtab !== "ledger" && list && list.samples.length === 0 && (
        <p className="py-12 text-center text-sm text-h-muted">No samples here yet.</p>
      )}
    </section>
  );
}
