from fastapi import FastAPI

from .auth.routes import router as auth_router
from .procurement.routes import router as proc_router
from .users.routes import router as users_router
from .workspaces.routes import router as ws_router

app = FastAPI(title="JoineryFlow API")
app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(users_router)
app.include_router(proc_router)


@app.get("/health")
def health():
    return {"ok": True}
