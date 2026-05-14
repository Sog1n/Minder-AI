from fastapi import APIRouter

from app.core.store import store

router = APIRouter()


@router.get("/dashboard")
async def dashboard():
    return store.metric_dashboard()

