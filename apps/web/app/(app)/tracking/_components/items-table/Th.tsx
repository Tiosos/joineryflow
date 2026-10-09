"use client";



export function Th({
  children,
  className = "",
  align = "left",
  sort,
  sortActive,
  sortAsc,
  onSort,
  title,
}: {
  children?: React.ReactNode;
  className?: string;
  align?: "left" | "right";
  sort?: boolean;
  sortActive?: boolean;
  sortAsc?: boolean;
  onSort?: () => void;
  title?: string;
}) {
  const alignClass = align === "right" ? "text-right" : "text-left";
  const sortIndicator = sort ? (
    <span className={`ml-1 inline-block text-[8px] ${sortActive ? "text-h-ink" : "text-h-line"}`}>
      {sortActive ? (sortAsc ? "▲" : "▼") : "↕"}
    </span>
  ) : null;
  return (
    <th
      className={`px-2 py-2 font-mono text-[10px] font-semibold uppercase tracking-wider ${alignClass} ${className} ${sort ? "cursor-pointer select-none hover:text-h-ink" : ""}`}
      onClick={onSort}
      title={title}
    >
      {children}
      {sortIndicator}
    </th>
  );
}
