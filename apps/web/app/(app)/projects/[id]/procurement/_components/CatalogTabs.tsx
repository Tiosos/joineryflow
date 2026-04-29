"use client";

interface CatalogTabsProps {
  projectId: string;
  userRole: string;
}

export default function CatalogTabs({
  projectId,
  userRole,
}: CatalogTabsProps) {
  return (
    <div className="p-6">
      <p className="text-h-muted">Catalog Tabs Stub</p>
      <p className="text-sm text-h-muted mt-2">
        projectId: {projectId}, userRole: {userRole}
      </p>
    </div>
  );
}
