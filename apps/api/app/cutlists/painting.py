"""Painting compatibility for shared cutlists; callers own the transaction."""
from sqlalchemy import text


def lock_project(db, project_id):
    # Separate namespace from business row locks. Acquire before locking items,
    # so two painting edits/links on different items cannot both pass validation.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('cutlist-paint:' || CAST(:p AS text), 0))"),
               {"p": project_id})


def incompatible(db, *, item_id, cutlist_id, painting_req, paint_after_assembly):
    if not cutlist_id or not painting_req:
        return False
    return db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM items WHERE cutlist_id=:c AND item_id<>:i
              AND NOT deleted AND row_type='joinery_item' AND painting_req
              AND COALESCE(paint_after_assembly, false) <> :after
        )
    """), {"c": cutlist_id, "i": item_id, "after": bool(paint_after_assembly)}).scalar_one()
