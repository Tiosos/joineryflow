"use client";

interface ProjectMaterialsTableProps {
  projectId: string;
  userRole: string;
}

export default function ProjectMaterialsTable({
  projectId,
  userRole,
}: ProjectMaterialsTableProps) {
  return (
    <div className="p-6">
      <p className="text-h-muted">Project Materials Table Stub</p>
      <p className="text-sm text-h-muted mt-2">
        projectId: {projectId}, userRole: {userRole}
      </p>
    </div>
  );
}
