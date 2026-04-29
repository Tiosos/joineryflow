"use client";

interface BatchesTableProps {
  projectId: string;
  userRole: string;
}

export default function BatchesTable({
  projectId,
  userRole,
}: BatchesTableProps) {
  return (
    <div className="p-6">
      <p className="text-h-muted">Batches Table Stub</p>
      <p className="text-sm text-h-muted mt-2">
        projectId: {projectId}, userRole: {userRole}
      </p>
    </div>
  );
}
