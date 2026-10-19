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

/** Numbers: the sheet size and thickness in mm (columns since `0001`, shown from the catalog now). Whole mm for the
 *  sheet, hundredths for the thickness. JSON numbers on the wire. */
export const BOARD_NUMBER_FIELDS = [
  { key: "sheet_len_mm", label: "Sheet length (mm)", step: "1" },
  { key: "sheet_wid_mm", label: "Sheet width (mm)", step: "1" },
  { key: "thickness_mm", label: "Thickness (mm)", step: "0.01" },
] as const;
