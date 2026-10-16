/** Edging's own fields (migration 0069), in the order the grid and the new-item form show them. */
export const EDGING_TEXT_FIELDS = [
  { key: "colour", label: "Colour" },
  { key: "edge_type", label: "Edge type" },
  { key: "um", label: "UM" },
  { key: "product_website", label: "Website" },
] as const;

/** Numbers: roll length in metres, width and thickness in mm. */
export const EDGING_NUMBER_FIELDS = [
  { key: "roll_length_m", label: "Roll length (m)" },
  { key: "edge_width_mm", label: "Width (mm)" },
  { key: "edge_thickness_mm", label: "Thickness (mm)" },
] as const;
