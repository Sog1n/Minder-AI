from fastapi import APIRouter, HTTPException

from app.core.store import public_dict, store
from app.schemas.api import WorkerCreateRequest

router = APIRouter()


@router.get("")
async def list_workers():
    return [public_dict(worker) for worker in store.workers.values()]


@router.post("")
async def create_worker(request: WorkerCreateRequest):
    if request.id in store.workers:
        raise HTTPException(status_code=409, detail="Worker already exists")
    worker = store.add_worker(
        request.id,
        request.name,
        request.department,
        request.seniority_years,
        request.trust_score,
    )
    return public_dict(worker)

