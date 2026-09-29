import { CommentThread } from "@/components/comments/CommentThread";

// The project's own thread (Plan V1 §29). Area and Room threads exist in the
// API but neither has a page of its own yet, so they have no surface here.
export function ProjectCommentsCard({
  projectId,
  currentUserId,
  currentUserRole,
  canComment,
}: {
  projectId: number;
  currentUserId: number | null;
  currentUserRole: string | null;
  canComment: boolean;
}) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Comments</h2>
      <CommentThread
        objectType="project"
        objectId={projectId}
        currentUserId={currentUserId}
        currentUserRole={currentUserRole}
        canComment={canComment}
      />
    </section>
  );
}
