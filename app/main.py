from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1 import admin, agent, conversation, knowledge, metrics, workers
from app.core.store import store

app = FastAPI(title="Minder AI Knowledge System", version="1.0.0-demo")


@app.on_event("startup")
async def startup() -> None:
    store.seed_defaults()


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(conversation.router, prefix="/api/v1/conversations", tags=["Conversations"])
app.include_router(workers.router, prefix="/api/v1/workers", tags=["Workers"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["Knowledge"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

