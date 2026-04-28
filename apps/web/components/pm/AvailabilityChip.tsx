interface Props {
  ready: number;
  blocked: number;
}

export function AvailabilityChip({ ready, blocked }: Props) {
  if (ready === 0 && blocked === 0) {
    return <span className="text-xs text-h-muted">no hardware</span>;
  }
  // all ready = good; any blocked = warn
  const tone = blocked === 0 ? "text-h-good" : "text-h-warn";
  return (
    <span className={`text-xs font-mono ${tone}`}>
      {ready} ready / {blocked} blocked
    </span>
  );
}
