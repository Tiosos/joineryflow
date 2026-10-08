"use client";



export function Field({ label, value, mono = false }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-h-muted">{label}</dt>
      <dd className={`text-h-ink ${mono ? "h-mono" : ""}`}>{value || "—"}</dd>
    </div>
  );
}
