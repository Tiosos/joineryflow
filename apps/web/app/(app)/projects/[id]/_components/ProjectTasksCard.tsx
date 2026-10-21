import { TaskPanel } from "@/components/tasks/TaskPanel";

// Tasks on the project itself and on any of its items and cutlists (Plan V1 §10, Q524).
// New tasks made here are on the project; an item's or cutlist's own task is made on its own page.
export function ProjectTasksCard({
  projectId,
  currentUserId,
  currentUserRole,
  canComment,
}: {
  projectId: number;
  currentUserId: number;
  currentUserRole: string;
  canComment: boolean;
}) {
  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4" data-testid="project-tasks">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Tasks</h2>
      <TaskPanel
        scope={{ kind: "project", projectId }}
        meId={currentUserId}
        meRole={currentUserRole}
        canCreate={canComment}
      />
    </section>
  );
}
