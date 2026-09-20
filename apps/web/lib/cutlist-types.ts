/**
 * Cutlist wire types.
 * Source: apps/api/app/cutlists/schemas.py
 *
 * The Cutlist is the entity Plan V1 Q438 made first-class: several Joinery
 * Items share one, and the production workflow belongs to it. Q474 settled
 * that its workspace is the existing `List` tab rather than a seventh primary
 * tab, which is why these live behind `/list`.
 */

export interface CutlistItemRow {
  item_id: number;
  item_number: number | null;
  code: string | null;
  description: string | null;
  status: string | null;
  room_no: string | null;
  room_desc: string | null;
}

export interface CutlistOut {
  cutlist_id: number;
  project_id: number;
  /** Six digits from the company-wide sequence (Q442/Q443) — never supplied by a caller. */
  cutlist_no: number;
  name: string | null;
  item_count: number;
  created_by: number | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * A part on the cutlist. Flat across the whole cutlist, each row naming its own
 * item, because several Joinery Items share one cutlist (Q410) and the sheet is
 * cut in one go — plan_v1.md §1218 / Q569.
 */
export interface CutlistPartRow {
  part_id: number;
  item_id: number;
  item_number: number | null;
  module_name: string | null;
  part_name: string | null;
  qty: number | null;
  len_mm: number | null;
  wid_mm: number | null;
  board_material: string | null;
  edge: string | null;
  colour: string | null;
  paint_instruction: string | null;
  comment: string | null;
}

export interface CutlistHardwareRow {
  line_id: number;
  item_id: number;
  item_number: number | null;
  catalog_description: string | null;
  catalog_supplier: string | null;
  catalog_source_table: string | null;
  qty: number | null;
  note: string | null;
}

export interface CutlistDetailOut extends CutlistOut {
  items: CutlistItemRow[];
  parts: CutlistPartRow[];
  hardware: CutlistHardwareRow[];
}

export interface CutlistListOut {
  project_id: number;
  cutlists: CutlistOut[];
}
