/** Board's own text fields (migration 0068; `um` 0075), in the order the grid and the new-item form show them. */
export const BOARD_TEXT_FIELDS = [
  { key: "colour", label: "Colour" },
  { key: "substrate", label: "Substrate" },
  { key: "finish", label: "Finish" },
  { key: "sided", label: "Sided" },
  { key: "grain", label: "Grain" },
  { key: "rating", label: "Rating" },
  { key: "hmr", label: "HMR" },
  { key: "um", label: "UM" },
  { key: "product_website", label: "Website" },
] as const;
