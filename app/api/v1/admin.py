from fastapi import APIRouter

from app.core.store import store
from app.schemas.api import SeedResponse

router = APIRouter()


@router.post("/seed", response_model=SeedResponse)
async def seed_defaults():
    store.seed_defaults()
    return SeedResponse(workers=len(store.workers), sop_documents=len(store.sop_documents))

