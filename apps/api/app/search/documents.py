"""Turn database rows into search documents (spec §3.1; plan task C1).

The only module that knows the source schema. One loader per outbox kind,
each a single `text()` query over a list of ids, returning
`{entity_id: document}` for the rows that should be indexed. An id that is
missing from the result — deleted, or excluded like a soft-deleted item — is a
document the worker must delete.

**Field allow-list (spec §3.3).** Every loader selects its columns by name.
Never indexed: password hashes, tokens, file bytes, money columns,
`vendors.bank_account` / `tax_id` / `payment_terms` / `rating`, customer
`abn`. `tests/test_search_documents.py` pins the document keys per type.

**`archived`** mirrors each record's own page (Q580): void / VOID items,
`archived_at` on drawings, samples, customers and catalog rows, plus what the
iSample and Estimating Archive subtabs already show — rejected samples and
rejected / expired / withdrawn estimates. Cancelled orders, inactive
suppliers and closed projects stay visible: no page archives them.
"""
from __future__ import annotations

from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..row_types import live_joinery_items

# Catalog table (= outbox kind) -> (catalog page tab, pk, legacy unique column,
# supplier expression, extra body columns). `custom_made` names its supplier
# column `vendor` (CLAUDE.md); 0017's `default_supplier` wins where set.
# The items loader deliberately covers both row types, so no joinery_items_only.
MATERIALS = {
    "board_materials": ("board", "material_id", "code",
                        "COALESCE(m.default_supplier, m.supplier)", []),
    "hardware_materials": ("hardware", "material_id", None,
                           "COALESCE(m.default_supplier, m.supplier)", ["m.brand", "m.hardware_type"]),
    "custom_made": ("custom_made", "material_id", "internal_ref",
                    "COALESCE(m.default_supplier, m.vendor)", []),
    "benchtop_materials": ("benchtop", "material_id", "slab_id",
                           "COALESCE(m.default_supplier, m.supplier)", ["m.material_type"]),
    "appliances": ("appliance", "material_id", "model_number",
                   "COALESCE(m.default_supplier, m.supplier)", ["m.manufacturer"]),
    "equipment_hire": ("hire", "hire_id", "contract_ref",
                       "COALESCE(m.default_supplier, m.supplier)", []),
    "edging_materials": ("edging", "material_id", None,
                         "COALESCE(m.default_supplier, m.supplier)", ["m.colour", "m.edge_type"]),
    "glass_materials": ("glass", "material_id", None,
                        "COALESCE(m.default_supplier, m.supplier)", ["m.colour", "m.glass_type"]),
    "timber_materials": ("timber", "material_id", None,
                         "COALESCE(m.default_supplier, m.supplier)", ["m.colour", "m.grain"]),
}

KINDS: tuple[str, ...] = (
    "project", "item", "cutlist", "order", "supplier", "drawing", "sample",
    "customer", "estimate", "task", *MATERIALS,
)


# kind -> (source table, primary key); mirrors migration 0033's SOURCES.
SOURCE_TABLES: dict[str, tuple[str, str]] = {
    "project": ("projects", "project_id"),
    "item": ("items", "item_id"),
    "cutlist": ("cutlist", "cutlist_id"),
    "order": ("purchase_orders", "po_id"),
    "supplier": ("vendors", "vendor_id"),
    "drawing": ("shop_drawing", "drawing_id"),
    "sample": ("sample", "sample_id"),
    "customer": ("customer", "customer_id"),
    "estimate": ("estimate", "estimate_id"),
    "task": ("task", "task_id"),
    **{k: (k, v[1]) for k, v in MATERIALS.items()},
}


def doc_ids(kind: str, entity_id: int) -> list[str]:
    """Every document id an outbox row may stand for — used to delete."""
    if kind == "item":
        return [f"item-{entity_id}", f"related_part-{entity_id}"]
    if kind in MATERIALS:
        return [f"material-{kind}-{entity_id}"]
    return [f"{kind}-{entity_id}"]


def _join(*parts) -> str:
    return " · ".join(str(p) for p in parts if p not in (None, ""))


def _words(*parts) -> str:
    return " ".join(str(p) for p in parts if p not in (None, ""))


def _codes(*parts) -> list[str]:
    """Distinct, in order — a seeded item's cutlist carries its own number."""
    return list(dict.fromkeys(str(p) for p in parts if p not in (None, "")))


def _epoch(ts) -> int:
    return int(ts.timestamp()) if ts is not None else 0


def _doc(*, type_, entity_id, id_=None, workspace_id, project_id=None,
         project_code=None, codes, title, subtitle="", body="", status=None,
         archived=False, updated_at=None, url=None, **extra) -> dict:
    return {
        **extra,
        "id": id_ or f"{type_}-{entity_id}",
        "type": type_,
        "entity_id": entity_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "project_code": project_code,
        "codes": codes,
        "title": title or "",
        "subtitle": subtitle,
        "body": body,
        "status": status,
        "archived": bool(archived),
        "updated_at": _epoch(updated_at),
        "url": url,
    }


def _rows(db: Session, sql: str, ids: list[int]):
    return db.execute(text(sql), {"ids": list(ids)}).mappings()


def _projects(db, ids):
    for r in _rows(db, """
        SELECT project_id, workspace_id, project_code, carell_pid, name, builder,
               classification, site_street, site_suburb, tg_project_manager,
               status, updated_at
          FROM projects WHERE project_id = ANY(:ids)""", ids):
        yield _doc(
            type_="project", entity_id=r["project_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(r["project_code"], r["carell_pid"]),
            title=r["name"], subtitle=_join(r["project_code"], r["builder"], r["site_suburb"]),
            body=_words(r["classification"], r["site_street"], r["tg_project_manager"]),
            status=r["status"], updated_at=r["updated_at"],
            url=f"/tracking?project_id={r['project_id']}",
        )


def _items(db, ids):
    # `stage` here is the legacy *site location* column (terminology pin),
    # still written beside area_id / room_id (Q435) — never a lifecycle stage.
    for r in _rows(db, """
        SELECT i.item_id, i.row_type, i.num, i.code, i.item_code, i.group_id,
               i.description, i.level, i.stage AS site_location, i.rm_desc,
               i.estimator_notes, i.related_part_type_key, i.status,
               i.void_flag, i.updated_at, i.project_id,
               p.workspace_id, p.project_code,
               a.name AS area_name, rm.rm_no, rm.rm_desc AS room_desc,
               c.cutlist_no
          FROM items i
          JOIN projects p ON p.project_id = i.project_id
          LEFT JOIN area a ON a.area_id = i.area_id
          LEFT JOIN room rm ON rm.room_id = i.room_id
          LEFT JOIN cutlist c ON c.cutlist_id = i.cutlist_id
         WHERE i.item_id = ANY(:ids)
           AND NOT COALESCE(i.deleted, false)""", ids):
        is_part = r["row_type"] == "related_part"
        type_ = "related_part" if is_part else "item"
        room = _words(r["rm_no"], r["room_desc"])
        yield _doc(
            type_=type_, entity_id=r["item_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(r["num"], r["code"], r["item_code"], r["group_id"], r["cutlist_no"]),
            title=r["description"] or r["code"],
            subtitle=_join(r["project_code"], r["area_name"], room, r["level"]),
            body=_words(r["estimator_notes"], r["site_location"], r["rm_desc"],
                        r["related_part_type_key"]),
            status=r["status"],
            archived=r["void_flag"] or r["status"] == "VOID",
            updated_at=r["updated_at"],
            url=(f"/tracking?project_id={r['project_id']}" if is_part
                 else f"/items/{r['item_id']}"),
        )


def _cutlists(db, ids):
    for r in _rows(db, """
        SELECT c.cutlist_id, c.cutlist_no, c.name, c.project_id, c.updated_at,
               p.workspace_id, p.project_code
          FROM cutlist c JOIN projects p ON p.project_id = c.project_id
         WHERE c.cutlist_id = ANY(:ids) AND NOT c.deleted""", ids):
        yield _doc(
            type_="cutlist", entity_id=r["cutlist_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(r["cutlist_no"]),
            title=r["name"] or f"Cutlist {r['cutlist_no']}",
            subtitle=_join(r["project_code"], "Cutlist"),
            updated_at=r["updated_at"],
            url=f"/list?project_id={r['project_id']}&cutlist={r['cutlist_id']}",
        )


def _orders(db, ids):
    # A project-less order reaches its workspace through its vendor (Q554).
    for r in _rows(db, """
        SELECT po.po_id, po.po_number, po.order_number, po.cutlist_no,
               po.supplier_ref_no, po.product_code, po.description,
               po.product_description, po.notes, po.internal_comments,
               po.status, po.updated_at, po.project_id,
               COALESCE(p.workspace_id, v.workspace_id) AS workspace_id,
               p.project_code, v.name AS vendor_name
          FROM purchase_orders po
          JOIN vendors v ON v.vendor_id = po.vendor_id
          LEFT JOIN projects p ON p.project_id = po.project_id
         WHERE po.po_id = ANY(:ids)""", ids):
        yield _doc(
            type_="order", entity_id=r["po_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(r["po_number"], r["order_number"], r["cutlist_no"],
                         r["supplier_ref_no"], r["product_code"]),
            title=r["description"],
            subtitle=_join(r["vendor_name"], r["project_code"], r["status"]),
            body=_words(r["product_description"], r["notes"], r["internal_comments"],
                        r["vendor_name"]),
            status=r["status"], updated_at=r["updated_at"],
            url=f"/orderbook?order={r['po_number']}",
        )


def _suppliers(db, ids):
    for r in _rows(db, """
        SELECT vendor_id, workspace_id, name, category, contact_name,
               contact_email, contact_phone, address, status, updated_at
          FROM vendors WHERE vendor_id = ANY(:ids)""", ids):
        yield _doc(
            type_="supplier", entity_id=r["vendor_id"], workspace_id=r["workspace_id"],
            codes=[], title=r["name"],
            subtitle=_join(r["category"], r["contact_name"], r["contact_phone"]),
            body=_words(r["contact_email"], r["address"]),
            status=r["status"], updated_at=r["updated_at"],
            url=None,  # no supplier page exists (Q579)
        )


def _drawings(db, ids):
    for r in _rows(db, """
        SELECT d.drawing_id, d.title, d.room, d.project_id, d.archived_at,
               d.created_at, d.drawing_no, d.joinery_id, p.workspace_id, p.project_code,
               rv.rev_no, rv.status AS rev_status
          FROM shop_drawing d
          JOIN projects p ON p.project_id = d.project_id
          LEFT JOIN shop_drawing_revision rv ON rv.revision_id = d.current_revision_id
         WHERE d.drawing_id = ANY(:ids)""", ids):
        yield _doc(
            type_="drawing", entity_id=r["drawing_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(f"SD-{r['drawing_id']:04d}", r["drawing_no"], r["joinery_id"]),
            title=r["title"],
            subtitle=_join(r["project_code"], r["room"],
                           f"Rev {r['rev_no']}" if r["rev_no"] else None),
            status=r["rev_status"], archived=r["archived_at"] is not None,
            updated_at=r["created_at"],
            url=f"/shop-dwgs?project={r['project_id']}&drawing={r['drawing_id']}",
        )


def _samples(db, ids):
    for r in _rows(db, """
        SELECT s.sample_id, s.title, s.room, s.supplier, s.status, s.review_note,
               s.archived_at, s.updated_at, s.project_id,
               p.workspace_id, p.project_code
          FROM sample s JOIN projects p ON p.project_id = s.project_id
         WHERE s.sample_id = ANY(:ids)""", ids):
        yield _doc(
            type_="sample", entity_id=r["sample_id"], workspace_id=r["workspace_id"],
            project_id=r["project_id"], project_code=r["project_code"],
            codes=_codes(f"SAM-{r['sample_id']:04d}"),
            title=r["title"], subtitle=_join(r["project_code"], r["room"], r["supplier"]),
            body=_words(r["review_note"]), status=r["status"],
            archived=r["archived_at"] is not None or r["status"] == "rejected",
            updated_at=r["updated_at"],
            url=f"/isample?project={r['project_id']}&sample={r['sample_id']}",
        )


def _customers(db, ids):
    for r in _rows(db, """
        SELECT customer_id, workspace_id, name, email, phone, billing_address,
               notes, archived_at, updated_at
          FROM customer WHERE customer_id = ANY(:ids)""", ids):
        yield _doc(
            type_="customer", entity_id=r["customer_id"], workspace_id=r["workspace_id"],
            codes=[], title=r["name"], subtitle=_join(r["email"], r["phone"]),
            body=_words(r["billing_address"], r["notes"]),
            archived=r["archived_at"] is not None, updated_at=r["updated_at"],
            url=f"/customers/{r['customer_id']}",
        )


def _estimates(db, ids):
    for r in _rows(db, """
        SELECT e.estimate_id, e.workspace_id, e.estimate_no, e.title,
               e.site_address, e.updated_at, cu.name AS customer_name,
               rv.rev_no, rv.status
          FROM estimate e
          JOIN customer cu ON cu.customer_id = e.customer_id
          LEFT JOIN estimate_revision rv ON rv.revision_id = e.current_revision_id
         WHERE e.estimate_id = ANY(:ids)""", ids):
        yield _doc(
            type_="estimate", entity_id=r["estimate_id"], workspace_id=r["workspace_id"],
            codes=_codes(r["estimate_no"]), title=r["title"],
            subtitle=_join(r["customer_name"],
                           f"Rev {r['rev_no']}" if r["rev_no"] else None, r["status"]),
            body=_words(r["site_address"]), status=r["status"],
            # Q580's "rejected / expired / withdrawn" was written against the
            # 6-state machine; Q548 collapsed rejected+expired onto LOST
            # under the 12-stage tender lifecycle (Q487/488).
            archived=r["status"] in ("LOST", "WITHDRAWN"),
            updated_at=r["updated_at"],
            url=f"/estimating/{r['estimate_id']}",
        )


def _materials(kind):
    tab, pk, legacy, supplier, extra = MATERIALS[kind]
    cols = ", ".join([f"m.{legacy} AS legacy" if legacy else "NULL AS legacy",
                      f"{supplier} AS supplier_name",
                      *(f"{c} AS extra{n}" for n, c in enumerate(extra))])
    project = "m.project_id" if kind == "equipment_hire" else "NULL::bigint"

    def load(db, ids):
        for r in _rows(db, f"""
            SELECT m.{pk} AS mid, m.workspace_id, m.sku, m.description, m.notes,
                   m.synonyms, m.archived_at, m.updated_at, {project} AS project_id,
                   {cols}
              FROM {kind} m WHERE m.{pk} = ANY(:ids)""", ids):
            extras = [r[f"extra{n}"] for n in range(len(extra))]
            yield _doc(
                type_="material", entity_id=r["mid"], id_=f"material-{kind}-{r['mid']}",
                workspace_id=r["workspace_id"], project_id=r["project_id"],
                codes=_codes(r["sku"], r["legacy"]), title=r["description"],
                subtitle=_join(tab.replace("_", " ").title(), r["supplier_name"]),
                body=_words(*(r["synonyms"] or []), *extras, r["notes"]),
                archived=r["archived_at"] is not None, updated_at=r["updated_at"],
                # The catalog page's q= matches description or sku, and some
                # rows carry no sku.
                url=f"/catalog?tab={tab}&q={quote(r['sku'] or r['description'] or '')}",
            )
    return load


_TASK_STATUS = {"open": "Open", "in_progress": "In progress", "done": "Done", "cancelled": "Cancelled"}


def _tasks(db, ids):
    """Tasks (migration 0080/0081). Besides the usual keys a task document carries `visibility`
    (`tracking` on a project or item, `list` on a cutlist, `private` with no target) and
    `private_to` (creator and assignee): the search filter keeps a private task from anyone else
    (`index.TaskScope`). A task whose item or cutlist is soft-deleted is not indexed, so it drops
    out of search exactly as it drops out of `/tasks`. Done and cancelled tasks are `archived`."""
    for r in _rows(db, f"""
        SELECT t.task_id, t.workspace_id, t.title, t.description, t.status, t.due_date,
               t.created_by, t.assignee_id, t.project_id, t.item_id, t.cutlist_id, t.updated_at,
               au.full_name AS assignee_name, cu.full_name AS creator_name,
               COALESCE(t.project_id, i.project_id, c.project_id) AS target_project_id,
               p.project_code, i.num AS item_num, i.code AS item_code,
               c.cutlist_no, c.name AS cutlist_name
          FROM task t
          LEFT JOIN app_user au ON au.id = t.assignee_id
          LEFT JOIN app_user cu ON cu.id = t.created_by
          LEFT JOIN items i ON i.item_id = t.item_id AND {live_joinery_items("i")}
          LEFT JOIN cutlist c ON c.cutlist_id = t.cutlist_id AND NOT c.deleted
          LEFT JOIN projects p ON p.project_id = COALESCE(t.project_id, i.project_id, c.project_id)
         WHERE t.task_id = ANY(:ids)
           AND (t.item_id IS NULL OR i.item_id IS NOT NULL)
           AND (t.cutlist_id IS NULL OR c.cutlist_id IS NOT NULL)""", ids):
        if r["item_id"] is not None:
            label = f"Item {r['item_code'] or r['item_num']}"
        elif r["cutlist_id"] is not None:
            label = f"Cutlist {r['cutlist_no']}"
        elif r["project_id"] is not None:
            label = f"Project {r['project_code']}"
        else:
            label = None
        yield _doc(
            type_="task", entity_id=r["task_id"], workspace_id=r["workspace_id"],
            project_id=r["target_project_id"], project_code=r["project_code"],
            codes=_codes(r["project_code"] if r["project_id"] is not None else None,
                         r["item_num"], r["item_code"], r["cutlist_no"]),
            title=r["title"],
            subtitle=_join(label, _TASK_STATUS[r["status"]],
                           f"Due {r['due_date']}" if r["due_date"] else None),
            body=_words(r["description"], r["assignee_name"], r["creator_name"]),
            status=r["status"], archived=r["status"] in ("done", "cancelled"),
            updated_at=r["updated_at"], url=f"/tasks?task={r['task_id']}",
            visibility=("tracking" if r["project_id"] is not None or r["item_id"] is not None
                        else "list" if r["cutlist_id"] is not None else "private"),
            private_to=sorted({u for u in (r["created_by"], r["assignee_id"]) if u is not None}),
        )


LOADERS = {
    "project": _projects, "item": _items, "cutlist": _cutlists, "order": _orders,
    "supplier": _suppliers, "drawing": _drawings, "sample": _samples,
    "customer": _customers, "estimate": _estimates, "task": _tasks,
    **{k: _materials(k) for k in MATERIALS},
}


def load(db: Session, kind: str, ids: list[int]) -> dict[int, dict]:
    """Current documents for `ids` of one kind, keyed by entity id."""
    if not ids:
        return {}
    # A row with no workspace can never pass the search filter (and is equally
    # invisible on its own page, which filters on workspace_id too) — seed
    # data carries four such catalog rows. Treat it as not indexable.
    return {d["entity_id"]: d for d in LOADERS[kind](db, ids)
            if d["workspace_id"] is not None}
