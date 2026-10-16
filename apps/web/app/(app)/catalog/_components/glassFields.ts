/** Glass's own fields (migration 0070), in the order the grid and the new-item form show them. */
export const GLASS_TEXT_FIELDS = [
  { key: "colour", label: "Colour" },
  { key: "edge_finish", label: "Edge finish" },
  { key: "glass_type", label: "Glass type" },
  { key: "power_point", label: "Power point" },
  { key: "um", label: "UM" },
  { key: "product_website", label: "Website" },
] as const;

/** Numbers: sizes in mm. */
export const GLASS_NUMBER_FIELDS = [
  { key: "length_mm", label: "Length (mm)" },
  { key: "width_mm", label: "Width (mm)" },
  { key: "thickness_mm", label: "Thickness (mm)" },
] as const;
