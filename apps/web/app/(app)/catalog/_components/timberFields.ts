/** Solid Timber's own fields (migration 0074), in the order the grid and the new-item form show them. */
export const TIMBER_TEXT_FIELDS = [
  { key: "colour", label: "Colour" },
  { key: "finish", label: "Finish" },
  { key: "grain", label: "Grain" },
  { key: "rating", label: "Rating" },
  { key: "um", label: "UM" },
  { key: "product_website", label: "Website" },
] as const;

/** Numbers: sizes in mm. */
export const TIMBER_NUMBER_FIELDS = [
  { key: "thickness_mm", label: "Thickness (mm)" },
  { key: "width_mm", label: "Width (mm)" },
  { key: "length_mm", label: "Length (mm)" },
] as const;
