from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.store import store
from app.schemas.api import AgentCorrectionRequest, AgentCorrectionResponse, AgentQueryRequest, AgentQueryResponse
from app.services.agent import answer_query
from app.services.extraction import run_extraction_pipeline

router = APIRouter()


@router.post("/query", response_model=AgentQueryResponse)
async def query_agent(request: AgentQueryRequest):
    if request.worker_id not in store.workers:
        raise HTTPException(status_code=404, detail="Worker not found")
    return await answer_query(request.worker_id, request.query, request.conversation_id)


@router.patch("/{query_log_id}/correct", response_model=AgentCorrectionResponse)
async def correct_agent_response(query_log_id: str, request: AgentCorrectionRequest, background_tasks: BackgroundTasks):
    log = store.query_logs.get(query_log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Query log not found")
    if request.worker_id not in store.workers:
        raise HTTPException(status_code=404, detail="Worker not found")
    log.was_corrected = True
    log.correction_text = request.correction_text
    for item_id in log.used_knowledge_ids:
        item = store.knowledge_items.get(item_id)
        if item:
            item.confidence_score = max(0.0, item.confidence_score - 0.05)
            store.add_audit(
                item.id,
                "WORKER",
                "TRUST_ADJUSTMENT_FROM_CORRECTION",
                request.worker_id,
                item.status,
                item.status,
                "Served knowledge was corrected by a worker.",
                {"query_log_id": query_log_id},
            )
    conversation = store.create_conversation(request.worker_id, request.correction_text)
    background_tasks.add_task(run_extraction_pipeline, conversation.id)
    return AgentCorrectionResponse(query_log_id=query_log_id, conversation_id=conversation.id, status="processing")

