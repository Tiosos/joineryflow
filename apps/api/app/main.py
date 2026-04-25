from fastapi import FastAPI

from .auth.routes import router as auth_router

app = FastAPI(title="JoineryFlow API")
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"ok": True}
