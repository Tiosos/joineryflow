import type { RevisionStatus } from "@/lib/shop-drawings-types";

const PALETTE: Record<RevisionStatus, string> = {
  draft:    "bg-h-line/40 text-h-muted",
  pending:  "bg-h-warn/15 text-h-warn",
  approved: "bg-h-good/15 text-h-good",
  rejected: "bg-h-bad/15 text-h-bad",
};

const LABEL: Record<RevisionStatus, string> = {
  draft: "Draft", pending: "Pending", approved: "Approved", rejected: "Rejected",
};

export default function StatusPill({ status }: { status: RevisionStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${PALETTE[status]}`}>
      {LABEL[status]}
    </span>
  );
}
