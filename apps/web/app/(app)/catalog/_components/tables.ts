import type { CatalogSlug } from "@/lib/catalog-types";

/** The six catalog tables behind the Catalog screen. A product type's items live in one of them. */
export type TableKey = "board" | "hardware" | "custom_made" | "benchtop" | "appliance" | "hire";

export const TABLE_KEYS: TableKey[] = ["board", "hardware", "custom_made", "benchtop", "appliance", "hire"];

export const TAB_TO_SLUG: Record<TableKey, CatalogSlug> = {
  board: "board-materials",
  hardware: "hardware-materials",
  custom_made: "custom-made",
  benchtop: "benchtop-materials",
  appliance: "appliances",
  hire: "equipment-hire",
};

export const TABLE_LABEL: Record<TableKey, string> = {
  board: "Board", hardware: "Hardware", custom_made: "Custom", benchtop: "Benchtop",
  appliance: "Appliances", hire: "Equipment Hire",
};
