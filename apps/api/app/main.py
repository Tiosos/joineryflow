from fastapi import FastAPI

from .auth.routes import router as auth_router
from .catalog.routes import router as catalog_router
from .cut_floor.routes import router as cut_floor_router
from .areas.routes import router as areas_router
from .cutlists.routes import router as cutlists_router
from .cv.routes import router as cv_router
from .estimating.routes import router as estimating_router
from .files.routes import router as files_router
from .public.routes import router as public_router
from .hardware_lines.routes import router as hardware_lines_router
from .parts.routes import router as parts_router
from .home.routes import router as home_router
from .item_attachments.routes import router as item_attachments_router
from .item_queries.routes import router as item_queries_router
from .items.routes import router as items_router
from .material_summaries.routes import router as material_summaries_router
from .material_takes.routes import router as material_takes_router
from .orders.routes import router as orders_router
from .printing.routes import router as printing_router
from .procurement.routes import router as proc_router
from .procurement_v1.allocations.routes import router as proc_v1_alloc_router
from .procurement_v1.batches.routes import router as proc_v1_batches_router
from .procurement_v1.materials.routes import router as proc_v1_materials_router
from .procurement_v1.queue.routes import router as proc_v1_queue_router
from .project_contacts.routes import router as project_contacts_router
from .project_lift_access.routes import router as project_lift_access_router
from .projects.routes import router as projects_router
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
app.include_router(related_parts_router)
app.include_router(suppliers_router)
app.include_router(cv_router)
app.include_router(files_router)
app.include_router(item_attachments_router)
app.include_router(printing_router)
app.include_router(samples_router)
app.include_router(search_router)
app.include_router(shop_dwgs_router)
app.include_router(shop_floor_router)
app.include_router(ws_router)
app.include_router(users_router)
app.include_router(me_router)
app.include_router(team_router)
app.include_router(proc_router)
app.include_router(proc_v1_materials_router)
app.include_router(proc_v1_batches_router)
app.include_router(proc_v1_alloc_router)
app.include_router(proc_v1_queue_router)
app.include_router(projects_router)
app.include_router(project_contacts_router)
app.include_router(project_lift_access_router)
app.include_router(items_router)
app.include_router(item_queries_router)
app.include_router(material_takes_router)
app.include_router(material_summaries_router)
app.include_router(hardware_lines_router)
app.include_router(parts_router)
app.include_router(home_router)
app.include_router(estimating_router)


@app.get("/health")
def health():
    return {"ok": True}
