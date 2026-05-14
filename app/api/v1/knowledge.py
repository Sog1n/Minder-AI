from fastapi import APIRouter, HTTPException, Query

from app.core.store import public_dict, store
from app.models.domain import KnowledgeStatus
from app.schemas.api import ConflictListResponse, KnowledgeListResponse, KnowledgeResolveRequest
from app.services.verification import values_conflict

router = APIRouter()


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(status: str | None = None, domain: str | None = None, limit: int = Query(20, ge=1, le=100)):
    items = list(store.knowledge_items.values())
    if status:
        items = [item for item in items if item.status.value == status]
    if domain:
        items = [item for item in items if item.structured_fact.get("domain") == domain]
    items = sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]
    return KnowledgeListResponse(items=[public_dict(item) for item in items], total=len(items))


@router.get("/review")
async def review_items(status: list[str] = Query(default=["ESCALATED", "QUARANTINED"])):
    allowed = set(status)
    return [public_dict(item) for item in store.knowledge_items.values() if item.status.value in allowed]


@router.get("/conflicts", response_model=ConflictListResponse)
async def conflicts():
    pairs = []
    items = list(store.knowledge_items.values())
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left.structured_fact.get("entity") != right.structured_fact.get("entity"):
                continue
            if left.structured_fact.get("attribute") != right.structured_fact.get("attribute"):
                continue
            if values_conflict(str(left.structured_fact.get("value", "")), str(right.structured_fact.get("value", ""))):
                pairs.append(
                    {
                        "item_a": public_dict(left),
                        "item_b": public_dict(right),
                        "similarity": 1.0,
                        "contradiction_explanation": "Same entity and attribute with different values.",
                        "recommended_action": "ESCALATE" if "safety" in {left.structured_fact.get("domain"), right.structured_fact.get("domain")} else "QUARANTINE_BOTH",
                    }
                )
    return ConflictListResponse(conflicts=pairs)


@router.patch("/{knowledge_id}/resolve")
async def resolve_knowledge(knowledge_id: str, request: KnowledgeResolveRequest):
    item = store.knowledge_items.get(knowledge_id)
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    mapping = {
        "VERIFY": KnowledgeStatus.VERIFIED,
        "REJECT": KnowledgeStatus.REJECTED,
        "SUPERSEDE": KnowledgeStatus.SUPERSEDED,
        "QUARANTINE": KnowledgeStatus.QUARANTINED,
    }
    updated = store.update_status(
        item,
        mapping[request.decision],
        request.note or f"Supervisor decision: {request.decision}",
        actor_type="SUPERVISOR",
        actor_id=request.supervisor_id,
        metadata={"applies_to_conflict_id": request.applies_to_conflict_id},
    )
    return public_dict(updated)

