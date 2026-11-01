from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .db import SessionLocal
from .meta import current_schema_version, expected_schema_head

from .auth.routes import router as auth_router
from .catalog.routes import router as catalog_router
from .comments.routes import router as comments_router
from .cut_floor.routes import router as cut_floor_router
from .areas.routes import router as areas_router
from .cutlists.routes import router as cutlists_router
from .cv.routes import router as cv_router
from .estimating.routes import router as estimating_router
from .files.routes import router as files_router
from .public.routes import router as public_router
from .hardware_lines.routes import router as hardware_lines_router
from .parts.routes import router as parts_router
from .permission_groups.routes import router as permission_groups_router
from .home.routes import router as home_router
from .item_attachments.routes import router as item_attachments_router
from .item_documents.routes import router as item_documents_router
from .item_duplicates.routes import router as item_duplicates_router
from .item_queries.routes import router as item_queries_router
from .items.routes import router as items_router
from .material_summaries.routes import router as material_summaries_router
from .material_takes.routes import router as material_takes_router
from .notifications.routes import router as notifications_router
from .tasks.routes import router as tasks_router
from .orders.attachments import router as order_attachments_router
from .orders.routes import router as orders_router
from .printing.routes import router as printing_router
from .order_tabs.glass import router as glass_router
from .order_tabs.routes import router as order_tabs_router
from .order_tabs.tg_solid import router as tg_solid_router
from .order_tabs.timber import router as timber_router
from .payment_methods.routes import router as payment_methods_router
from .purchase_orders.routes import router as purchase_orders_router
from .procurement_v1.allocations.routes import router as proc_v1_alloc_router
from .procurement_v1.batches.routes import router as proc_v1_batches_router
from .procurement_v1.materials.routes import router as proc_v1_materials_router
from .procurement_v1.queue.routes import router as proc_v1_queue_router
from .project_contacts.routes import router as project_contacts_router
from .project_contracts.routes import router as project_contracts_router
from .project_lift_access.routes import router as project_lift_access_router
from .projects.routes import router as projects_router
from .qc.routes import router as qc_router
from .related_parts.routes import router as related_parts_router
from .samples.routes import router as samples_router
from .search.routes import router as search_router
from .shop_drawings.routes import router as shop_dwgs_router
from .suppliers.routes import router as suppliers_router
from .shop_floor.routes import router as shop_floor_router
from .users.routes import (
    router as users_router,
    me_router as me_router,
    team_router as team_router,
)
from .workspaces.routes import router as ws_router

app = FastAPI(title="JoineryFlow API")
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(cut_floor_router)
app.include_router(areas_router)
app.include_router(cutlists_router)
app.include_router(orders_router)
app.include_router(order_attachments_router)
app.include_router(order_tabs_router)
app.include_router(glass_router)
app.include_router(timber_router)
app.include_router(tg_solid_router)
app.include_router(payment_methods_router)
app.include_router(purchase_orders_router)
app.include_router(related_parts_router)
app.include_router(suppliers_router)
app.include_router(cv_router)
app.include_router(files_router)
app.include_router(item_attachments_router)
app.include_router(item_documents_router)
app.include_router(item_duplicates_router)
app.include_router(printing_router)
app.include_router(samples_router)
app.include_router(search_router)
app.include_router(shop_dwgs_router)
app.include_router(shop_floor_router)
app.include_router(ws_router)
app.include_router(users_router)
app.include_router(me_router)
app.include_router(team_router)
app.include_router(proc_v1_materials_router)
app.include_router(proc_v1_batches_router)
app.include_router(proc_v1_alloc_router)
app.include_router(proc_v1_queue_router)
app.include_router(projects_router)
app.include_router(project_contacts_router)
app.include_router(project_contracts_router)
app.include_router(project_lift_access_router)
app.include_router(items_router)
app.include_router(item_queries_router)
app.include_router(material_takes_router)
app.include_router(material_summaries_router)
app.include_router(hardware_lines_router)
app.include_router(parts_router)
app.include_router(permission_groups_router)
app.include_router(home_router)
app.include_router(estimating_router)
app.include_router(qc_router)
app.include_router(comments_router)
app.include_router(notifications_router)
app.include_router(tasks_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/health/live")
def health_live():
    return {"ok": True}


@app.get("/health/ready")
def health_ready():
    """Admit-traffic probe: the database answers AND its schema is at the head
    this image was built with. A new image on an old schema must read
    unhealthy, not serve 500s silently (Phase 0 §2, Q2 gate 3).

    200 on healthy, 503 otherwise; the body names the failing check either
    way so a human (or a load balancer log) can see why."""
    checks: dict = {}
    try:
        with SessionLocal() as db:
            checks["db"] = db.execute(text("SELECT 1")).scalar() == 1
            db_schema = current_schema_version(db)
    except Exception:
        checks["db"] = False
        db_schema = None

    head = expected_schema_head()
    checks["expected_schema_head"] = head
    checks["db_schema"] = db_schema
    if head is None:
        # Migration scripts not shipped with this process — cannot verify.
        checks["schema_match"] = "skipped"
    else:
        checks["schema_match"] = db_schema == [head]

    ok = checks["db"] is True and checks["schema_match"] in (True, "skipped")
    return JSONResponse({"ok": ok, "checks": checks}, status_code=200 if ok else 503)


@app.get("/version")
def version():
    """Support-facing identity: image tag, the schema head this build expects,
    and the revision the database is actually on. Never 500s — this endpoint
    exists to be answerable when things are broken."""
    try:
        with SessionLocal() as db:
            db_schema = current_schema_version(db)
    except Exception:
        db_schema = None
    return {
        "version": settings.app_version,
        "schema_head": expected_schema_head(),
        "db_schema": db_schema,
    }
