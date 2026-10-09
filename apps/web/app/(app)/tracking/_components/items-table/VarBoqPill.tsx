"use client";



export function VarBoqPill({ value }: { value: "BOQ" | "VAR" }) {
  const isVar = value === "VAR";
  const cls = isVar
    ? "bg-[#f3e0d6] text-[#a84f31]"
    : "bg-h-bg text-h-muted border border-h-line";
  return (
    <span className={`inline-block rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${cls}`}>
      {value}
    </span>
  );
}
