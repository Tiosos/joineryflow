function pad4(n: number): string { return String(n).padStart(4, "0"); }

export default function SampleIdChip({ sampleId }: { sampleId: number }) {
  return (
    <span className="h-mono inline-flex items-center rounded bg-white/90 px-1.5 py-0.5 text-[11px] font-semibold text-h-ink">
      #SAM-{pad4(sampleId)}
    </span>
  );
}
