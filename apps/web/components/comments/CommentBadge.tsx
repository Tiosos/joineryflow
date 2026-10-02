/** "💬 N" chip for a thread's live comment count (replies included); nothing at 0.
 *  Same look as the Areas & Rooms card's own badge on `/projects/[id]`. */
export function CommentBadge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span
      data-testid="comment-badge"
      className="shrink-0 rounded-full bg-h-accent-soft px-1.5 text-[10px] font-semibold text-h-ink"
      title={`${n} comment${n === 1 ? "" : "s"}`}
    >
      💬 {n}
    </span>
  );
}
