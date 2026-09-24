"""Cutlist query layer.

Routes own the transaction boundary (`db.commit`); queries flush only, matching
`samples/` and `items/`. Workspace isolation goes through
`projects.workspace_id` (the post-`0014` pattern), never a denormalised column.

Four rules from Plan V1 §B are enforced here rather than by the schema, because
a CHECK cannot reach another table:

* **Q411** — an item links to at most one cutlist. The column is single-valued,
  so the database cannot express "already taken"; linking an item that already
  holds a *different* cutlist returns `ITEM_HAS_CUTLIST` rather than silently
  reassigning it.
* **Q444** — a cutlist belongs to exactly one project. The FK pins the cutlist
  to a project; this layer additionally refuses to link an item from a
  different one.
* **Q447/Q417** — a related part never holds a cutlist. `0028` has a CHECK for
  it, but hitting a raw constraint violation gives the caller a 500; this
  layer refuses the link first.
* **Q539** — linking an item to a cutlist whose stages are already complete
  does **not** backfill `item_stages`. There is deliberately no code for it:
  the item stays blank and catches up at the next completion. Do not "fix" it.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from ..orders.queries import sync_orders_for_item
from ..row_types import joinery_items_only
from .schemas import CreateCutlistIn, PatchCutlistIn

_JOINERY_I = joinery_items_only("i")

# Shape returned by both the list and the detail read.
_CUTLIST_COLS = """
    c.cutlist_id,
    c.project_id,
    c.cutlist_no,
    c.name,
    c.created_by,
    u.full_name AS created_by_name,
    c.created_at,
    c.updated_at,
    (
        SELECT COUNT(*) FROM items li
        WHERE li.cutlist_id = c.cutlist_id
    ) AS item_count
"""


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def _cutlist_row(db: Session, *, cutlist_id: int, workspace_id: int) -> dict | None:
    """Fetch one cutlist, workspace-scoped. None means 404."""
    row = db.execute(
        text(
            f"""
            SELECT {_CUTLIST_COLS}
            FROM cutlist c
            JOIN projects p ON p.project_id = c.project_id
            LEFT JOIN app_user u ON u.id = c.created_by
            WHERE c.cutlist_id = :cid AND p.workspace_id = :w
            """
        ),
        {"cid": cutlist_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def list_cutlists(db: Session, *, project_id: int, workspace_id: int) -> dict | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None
    rows = db.execute(
        text(
            f"""
            SELECT {_CUTLIST_COLS}
            FROM cutlist c
            LEFT JOIN app_user u ON u.id = c.created_by
            WHERE c.project_id = :p
            ORDER BY c.cutlist_no
            """
        ),
        {"p": project_id},
    ).mappings().all()
    return {"project_id": project_id, "cutlists": [dict(r) for r in rows]}


def get_cutlist(db: Session, *, cutlist_id: int, workspace_id: int) -> dict | None:
    row = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    if row is None:
        return None
    items = db.execute(
        text(
            f"""
            SELECT i.item_id,
                   i.num       AS item_number,
                   i.code,
                   i.description,
                   i.status,
                   i.rm_no     AS room_no,
                   i.rm_desc   AS room_desc
            FROM items i
            WHERE i.cutlist_id = :cid
              AND {_JOINERY_I}
            ORDER BY COALESCE(i.num, CAST(i.item_id AS integer))
            """
        ),
        {"cid": cutlist_id},
    ).mappings().all()
    row["items"] = [dict(r) for r in items]

    # `plan_v1.md` §1218 (Q569): the cutlist details show the parts, components
    # and hardware themselves, not just which items are on the list — a cutlist
    # is what the shop cuts, so its contents are the point of opening it.
    #
    # Rolled up FLAT across the cutlist's items, each row naming its own item,
    # rather than nested per item: several Joinery Items share one cutlist
    # (Q410) and the whole sheet is cut in one go, so the useful order is the
    # cut order. The per-item view already exists in the drafter editor.
    row["parts"] = [
        dict(r)
        for r in db.execute(
            text(
                f"""
                SELECT p.part_id,
                       i.item_id,
                       i.num            AS item_number,
                       m.name           AS module_name,
                       p.part_name,
                       p.qty,
                       p.len_mm,
                       p.wid_mm,
                       bm.description   AS board_material,
                       p.edge,
                       p.colour,
                       p.paint_instruction,
                       p.comment
                FROM items i
                JOIN modules m         ON m.item_id = i.item_id
                JOIN parts p           ON p.module_id = m.module_id
                LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
                WHERE i.cutlist_id = :cid
                  AND {_JOINERY_I}
                ORDER BY COALESCE(i.num, CAST(i.item_id AS integer)),
                         m.module_id, p.part_id
                """
            ),
            {"cid": cutlist_id},
        ).mappings().all()
    ]

    # Hardware resolves through project_hardware_catalog exactly as the item
    # editor does — the six source tables keep their own PK and supplier column
    # names, which is why this CTE exists rather than a plain join.
    row["hardware"] = [
        dict(r)
        for r in db.execute(
            text(
                f"""
                -- Two traps here, both documented as invariants in CLAUDE.md:
                -- `custom_made` names its supplier column `vendor`, and the six
                -- tables' free-text `supplier` is mostly empty because `0017`
                -- put the real value in `default_supplier`. COALESCE, or every
                -- row reads as "no supplier" when one is plainly recorded.
                WITH src AS (
                    SELECT 'BOARD' AS t, material_id AS sid, description,
                           COALESCE(supplier, default_supplier) AS supplier
                    FROM board_materials
                    UNION ALL
                    SELECT 'HARDWARE', material_id, description,
                           COALESCE(supplier, default_supplier)
                    FROM hardware_materials
                    UNION ALL
                    SELECT 'CUSTOM', material_id, description,
                           COALESCE(vendor, default_supplier)
                    FROM custom_made
                    UNION ALL
                    SELECT 'BENCHTOP', material_id, description,
                           COALESCE(supplier, default_supplier)
                    FROM benchtop_materials
                    UNION ALL
                    SELECT 'APPLIANCE', material_id, description,
                           COALESCE(supplier, default_supplier)
                    FROM appliances
                    UNION ALL
                    SELECT 'HIRE', hire_id, description,
                           COALESCE(supplier, default_supplier)
                    FROM equipment_hire
                )
                SELECT hl.line_id,
                       i.item_id,
                       i.num              AS item_number,
                       src.description    AS catalog_description,
                       src.supplier       AS catalog_supplier,
                       phc.material_type  AS catalog_source_table,
                       hl.qty,
                       hl.note
                FROM items i
                JOIN item_hardware_lines hl ON hl.item_id = i.item_id
                LEFT JOIN project_hardware_catalog phc ON phc.catalog_id = hl.catalog_id
                LEFT JOIN src ON src.t = phc.material_type AND src.sid = phc.material_id
                WHERE i.cutlist_id = :cid
                  AND {_JOINERY_I}
                ORDER BY COALESCE(i.num, CAST(i.item_id AS integer)), hl.line_id
                """
            ),
            {"cid": cutlist_id},
        ).mappings().all()
    ]
    return row


def create_cutlist(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: CreateCutlistIn,
    actor_id: int,
) -> dict | None:
    """Allocate a cutlist. Returns None if the project is not in the workspace.

    Q442/Q443: the number is system-allocated from the company-wide
    `joinery_number_seq`, taken INSIDE the INSERT so two concurrent creates
    can never be handed the same one (see B2a).
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    cutlist_id = db.execute(
        text(
            """
            INSERT INTO cutlist (project_id, cutlist_no, name, created_by)
            VALUES (:p, nextval('joinery_number_seq'), :n, :a)
            RETURNING cutlist_id
            """
        ),
        {"p": project_id, "n": payload.name, "a": actor_id},
    ).scalar()
    db.flush()

    row = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="cutlist.create",
        target=str(cutlist_id),
        payload={"project_id": project_id, "cutlist_no": row["cutlist_no"]},
    )
    return row


def patch_cutlist(
    db: Session,
    *,
    cutlist_id: int,
    workspace_id: int,
    payload: PatchCutlistIn,
    actor_id: int,
) -> dict | None:
    """Rename only. `cutlist_no` is system-allocated (Q442) and never editable."""
    current = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    if current is None:
        return None

    fields = payload.model_dump(exclude_unset=True)
    if "name" not in fields:
        return current

    db.execute(
        text("UPDATE cutlist SET name = :n, updated_at = now() WHERE cutlist_id = :cid"),
        {"n": payload.name, "cid": cutlist_id},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="cutlist.update",
        target=str(cutlist_id),
        payload={"field": "name", "old": current["name"], "new": payload.name},
    )
    return _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)


def delete_cutlist(
    db: Session, *, cutlist_id: int, workspace_id: int, actor_id: int
) -> str:
    """'OK' | 'NOT_FOUND' | 'HAS_ITEMS'.

    A cutlist holding items is not deleted. The FK is ON DELETE SET NULL, so a
    delete would silently strip the number off every linked item — the same
    situation #4 refuses for a batch with allocations. Unlink first.
    """
    current = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"
    if current["item_count"]:
        return "HAS_ITEMS"

    db.execute(
        text("DELETE FROM cutlist WHERE cutlist_id = :cid"), {"cid": cutlist_id}
    )
    db.flush()
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="cutlist.delete",
        target=str(cutlist_id),
        payload={"cutlist_no": current["cutlist_no"], "project_id": current["project_id"]},
    )
    return "OK"


def _item_for_link(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    """Item row needed to validate a link. Includes related parts on purpose:
    the caller must be able to tell 'not here' from 'not a Joinery Item'."""
    row = db.execute(
        text(
            """
            SELECT i.item_id, i.num, i.project_id, i.row_type, i.cutlist_id
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid AND p.workspace_id = :w
            """
        ),
        {"iid": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def link_item(
    db: Session, *, cutlist_id: int, item_id: int, workspace_id: int, actor_id: int
) -> tuple[str, dict | None]:
    """Link an item to a cutlist.

    Returns (code, detail). Codes:
      OK               — linked (or already linked to this cutlist; idempotent)
      NOT_FOUND        — cutlist or item not in this workspace
      RELATED_PART     — related parts get no cutlist number (Q417)
      WRONG_PROJECT    — item belongs to another project (Q444)
      ITEM_HAS_CUTLIST — already on a different cutlist (Q411); detail carries it
    """
    cutlist = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    if cutlist is None:
        return "NOT_FOUND", None

    item = _item_for_link(db, item_id=item_id, workspace_id=workspace_id)
    if item is None:
        return "NOT_FOUND", None
    if item["row_type"] != "joinery_item":
        return "RELATED_PART", None
    if item["project_id"] != cutlist["project_id"]:
        return "WRONG_PROJECT", {"item_project_id": item["project_id"],
                                 "cutlist_project_id": cutlist["project_id"]}

    if item["cutlist_id"] == cutlist_id:
        return "OK", cutlist                       # idempotent re-link
    if item["cutlist_id"] is not None:
        existing = _cutlist_row(
            db, cutlist_id=item["cutlist_id"], workspace_id=workspace_id
        )
        return "ITEM_HAS_CUTLIST", {
            "cutlist_id": item["cutlist_id"],
            "cutlist_no": existing["cutlist_no"] if existing else None,
        }

    db.execute(
        text("UPDATE items SET cutlist_id = :cid, updated_at = now() WHERE item_id = :iid"),
        {"cid": cutlist_id, "iid": item_id},
    )
    db.flush()

    # Q539: no item_stages backfill. The item catches up at the next completion.
    #
    # Q430/Q431: the item now has a cutlist number, so every order that
    # references it — its own, and its related parts' (Q428) — is brought into
    # step. Blank references get filled (Q430); existing ones follow a
    # replacement (Q431), each with its previous value kept in the audit row.
    synced = sync_orders_for_item(
        db, item_id=item_id, workspace_id=workspace_id, actor_id=actor_id
    )
    write_edit_log(
        db, item_id=item_id, actor_id=actor_id,
        field="cutlist_id", old_value=None, new_value=str(cutlist["cutlist_no"]),
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="cutlist.link_item",
        target=str(cutlist_id),
        payload={"item_id": item_id, "cutlist_no": cutlist["cutlist_no"],
                 "orders_synced": [o["po_id"] for o in synced]},
    )
    return "OK", _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)


def unlink_item(
    db: Session, *, cutlist_id: int, item_id: int, workspace_id: int, actor_id: int
) -> str:
    """'OK' | 'NOT_FOUND' | 'NOT_LINKED'."""
    cutlist = _cutlist_row(db, cutlist_id=cutlist_id, workspace_id=workspace_id)
    if cutlist is None:
        return "NOT_FOUND"
    item = _item_for_link(db, item_id=item_id, workspace_id=workspace_id)
    if item is None:
        return "NOT_FOUND"
    if item["cutlist_id"] != cutlist_id:
        return "NOT_LINKED"

    db.execute(
        text("UPDATE items SET cutlist_id = NULL, updated_at = now() WHERE item_id = :iid"),
        {"iid": item_id},
    )
    db.flush()

    # The reference follows the item in both directions (Q431): losing the
    # cutlist blanks the order's CUTLIST NO. rather than leaving it stale.
    synced = sync_orders_for_item(
        db, item_id=item_id, workspace_id=workspace_id, actor_id=actor_id
    )
    write_edit_log(
        db, item_id=item_id, actor_id=actor_id,
        field="cutlist_id", old_value=str(cutlist["cutlist_no"]), new_value=None,
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="cutlist.unlink_item",
        target=str(cutlist_id),
        payload={"item_id": item_id, "cutlist_no": cutlist["cutlist_no"],
                 "orders_synced": [o["po_id"] for o in synced]},
    )
    return "OK"
