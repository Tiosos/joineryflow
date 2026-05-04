import type { SampleStatus } from "@/lib/samples-types";

const PALETTE: Record<SampleStatus | "archived", string> = {
  pending:  "bg-amber-100 text-amber-900",
  approved: "bg-emerald-100 text-emerald-900",
  rejected: "bg-rose-100 text-rose-900",
  archived: "bg-h-line/40 text-h-muted line-through",
};

const LABEL: Record<SampleStatus | "archived", string> = {
  pending: "Pending", approved: "Approved", rejected: "Rejected", archived: "Archived",
};

interface Props { status: SampleStatus; archived: boolean; }

export default function SampleStatusPill({ status, archived }: Props) {
  const key = archived ? "archived" : status;
  return (
    <span className={`inline-flex items-center rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${PALETTE[key]}`}>
      {LABEL[key]}
    </span>
  );
}
