/** Laminate Benchtop's own fields (migration 0071, on benchtop_materials), in the order the grid and the form show them. */
export const BENCHTOP_TEXT_FIELDS = [
  { key: "colour", label: "Colour" },
  { key: "underside", label: "Underside" },
  { key: "edge_details", label: "Edge details" },
  { key: "laminate_supplier", label: "Laminate supplier" },
  { key: "laminate_code", label: "Laminate code" },
  { key: "finish", label: "Finish" },
  { key: "um", label: "UM" },
  { key: "product_website", label: "Website" },
] as const;

/** Numbers: bench size in mm, then counts. */
export const BENCHTOP_NUMBER_FIELDS = [
  { key: "bench_length_mm", label: "Bench length (mm)", step: "0.01" },
  { key: "bench_width_mm", label: "Bench width (mm)", step: "0.01" },
  { key: "thickness_mm", label: "Thickness (mm)", step: "0.01" },
  { key: "pieces", label: "Pieces", step: "1" },
  { key: "joins", label: "Joins", step: "1" },
  { key: "cable_entry", label: "Cable entry", step: "1" },
] as const;
