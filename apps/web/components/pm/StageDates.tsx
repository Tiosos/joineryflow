import type { StageDates as StageDatesData } from "@/lib/pm-types";

const STAGE_KEYS = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "DEL", "INST",
] as const;

interface Props {
  stages: Record<string, StageDatesData>;
}

export function StageDates({ stages }: Props) {
  return (
    <>
      {STAGE_KEYS.map((key) => {
        const sd = stages[key];
        const due = sd?.due_date;
        const done = sd?.done_date;
        // Prefer done date; fall back to due date; "—" if neither.
        const display = done ? done : due ? due : "—";
        const tone = done
          ? "text-h-good"
          : due && new Date(due) < new Date()
            ? "text-h-bad" // overdue
            : "text-h-muted";
        return (
          <td
            key={key}
            className={`px-2 py-1.5 text-center font-mono text-xs ${tone}`}
          >
            {display === "—" ? "—" : display.slice(5)}
          </td>
        );
      })}
    </>
  );
}
