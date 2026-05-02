export default function VersionChip({ revNo }: { revNo: number }) {
  return (
    <span className="h-mono inline-flex items-center rounded border border-h-line bg-h-surface px-1.5 py-0.5 text-xs text-h-muted">
      v{revNo}
    </span>
  );
}
