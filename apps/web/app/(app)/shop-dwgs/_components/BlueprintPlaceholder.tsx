function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Props { seed: number; }

export default function BlueprintPlaceholder({ seed }: Props) {
  const rng = mulberry32(seed || 1);
  const titleY = 24 + rng() * 8;
  const dimX = 60 + rng() * 200;
  const dimY = 90 + rng() * 60;
  const dimLen = 60 + rng() * 120;

  return (
    <svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice"
         className="block h-full w-full bg-h-surface">
      <defs>
        <pattern id={`grid-${seed}`} width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M 16 0 L 0 0 0 16" fill="none" stroke="currentColor" strokeWidth="0.5" className="text-h-line" />
        </pattern>
      </defs>
      <rect width="320" height="200" fill={`url(#grid-${seed})`} />
      <line x1="20" y1={titleY} x2="300" y2={titleY} stroke="currentColor" strokeWidth="1" className="text-h-line" />
      {/* dimension callout */}
      <line x1={dimX} y1={dimY} x2={dimX + dimLen} y2={dimY} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
      <line x1={dimX} y1={dimY - 4} x2={dimX} y2={dimY + 4} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
      <line x1={dimX + dimLen} y1={dimY - 4} x2={dimX + dimLen} y2={dimY + 4} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
    </svg>
  );
}
