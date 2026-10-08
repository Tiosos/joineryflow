"use client";

import type { Line, StageKey } from "@/lib/estimating-types";
import { STAGE_KEYS } from "./shared";

export function LabourEditor({
  line, onSet, onClose,
}: {
  line: Line;
  onSet: (stage: StageKey, hours: number) => Promise<void>;
  onClose: () => void;
}) {
  const byStage = new Map(line.labour.map((l) => [l.stage_key, l.hours]));

  return (
    <div className="mt-2 grid grid-cols-2 gap-2 rounded border border-h-line bg-white p-3 text-xs md:grid-cols-5">
      <div className="col-span-full flex items-center justify-between">
        <span className="font-semibold">Labour hours per stage</span>
        <button type="button" onClick={onClose} className="text-h-muted hover:text-h-ink">×</button>
      </div>
      {STAGE_KEYS.map((sk) => (
        <label key={sk} className="flex flex-col">
          <span className="text-h-muted">{sk}</span>
          <input
            type="number"
            min={0}
            step="0.25"
            defaultValue={byStage.get(sk) ?? "0"}
            onBlur={(e) => onSet(sk, Number(e.target.value || 0))}
            className="mt-1 rounded border border-h-line px-1 py-0.5 font-mono"
            data-testid={`labour-${line.line_id}-${sk}`}
          />
        </label>
      ))}
    </div>
  );
}
