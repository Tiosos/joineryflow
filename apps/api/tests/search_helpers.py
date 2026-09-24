"""Shared row builders for the search tests (not a test module)."""
from sqlalchemy import text


def make_tree(db, workspace_id, code="SRCH-1"):
    """project → area → room, a cutlist and an item linked to all."""
    one = lambda sql, **p: db.execute(text(sql), p).scalar()  # noqa: E731
    pid = one("INSERT INTO projects(project_code, name, workspace_id)"
              " VALUES (:code, 'Search project', :w) RETURNING project_id", w=workspace_id, code=code)
    aid = one("INSERT INTO area(project_id, name) VALUES (:p, 'Level 2') RETURNING area_id", p=pid)
    rid = one("INSERT INTO room(area_id, rm_no, rm_desc) VALUES (:a, '2.04', 'Kitchen')"
              " RETURNING room_id", a=aid)
    cid = one("INSERT INTO cutlist(project_id, cutlist_no, name)"
              " VALUES (:p, nextval('joinery_number_seq'), 'Run') RETURNING cutlist_id", p=pid)
    iid = one("""INSERT INTO items(num, project_id, description, status, area_id, room_id, cutlist_id)
                 VALUES (nextval('joinery_number_seq'), :p, 'Island bench', 'LIVE', :a, :r, :c)
                 RETURNING item_id""", p=pid, a=aid, r=rid, c=cid)
    return {"w": workspace_id, "project": pid, "area": aid, "room": rid,
            "cutlist": cid, "item": iid}


def make_vendor(db, w, name):
    return db.execute(text("INSERT INTO vendors(workspace_id, name, category)"
                           " SELECT :w, :n, category_key FROM order_category LIMIT 1"
                           " RETURNING vendor_id"),
                      {"w": w, "n": name}).scalar()


def make_order(db, w, vid, po_number, project_id=None):
    uid = db.execute(text(
        "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
        " VALUES (:w, :e, 'Req', 'x', 'manager') RETURNING id"),
        {"w": w, "e": f"{po_number.lower()}@search.test"}).scalar()
    cat = db.execute(text("SELECT category_key FROM order_category LIMIT 1")).scalar()
    return db.execute(text("""
        INSERT INTO purchase_orders(po_number, vendor_id, project_id, requester_id,
                                    description, category)
        VALUES (:n, :v, :p, :u, 'Stone top', :c) RETURNING po_id"""),
        {"n": po_number, "v": vid, "p": project_id, "u": uid, "c": cat}).scalar()
