from fastapi import FastAPI

app = FastAPI(title="JoineryFlow API")

@app.get("/health")
def health():
    return {"ok": True}
