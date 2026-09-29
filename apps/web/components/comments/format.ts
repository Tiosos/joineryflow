/** An API timestamp (timezone-aware ISO) in the viewer's own zone. The API
 *  sends UTC; slicing the string would show server time to everyone. */
export function formatLocalTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
