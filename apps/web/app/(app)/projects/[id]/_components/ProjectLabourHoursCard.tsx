import type { ProjectLabourHoursOut } from "@/lib/pm-types";

// project_labour_hours_view always returns zero today (migration 0036) — a
// future labour-hours integration populates it. Same "not integrated yet"
// framing as ProjectDetailModal.tsx's HoursTable for the TGPAY-sourced tables.
export function ProjectLabourHoursCard({ hours }: { hours: ProjectLabourHoursOut }) {
  const rows: { label: string; value: number }[] = [
    { label: "Site install", value: hours.site_install },
    { label: "Assembly", value: hours.assembly },
    { label: "Administration", value: hours.administration },
  ];

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Labour Hours</h2>
      <div className="grid grid-cols-3 gap-3 text-sm">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              {r.label}
            </div>
            <div className="mt-0.5 font-mono tabular-nums text-h-ink">{r.value}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs italic text-h-muted">
        Not integrated yet — hours will come from a future labour-hours source.
      </p>
    </section>
  );
}
