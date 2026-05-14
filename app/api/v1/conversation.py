from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.store import store
from app.models.domain import ExtractionStatus
from app.schemas.api import ConversationIngestRequest, ConversationIngestResponse, ConversationStatusResponse
from app.services.extraction import run_extraction_pipeline

router = APIRouter()


@router.post("/ingest", status_code=202, response_model=ConversationIngestResponse)
async def ingest_conversation(request: ConversationIngestRequest, background_tasks: BackgroundTasks):
    if request.worker_id not in store.workers:
        raise HTTPException(status_code=404, detail="Worker not found")
    conversation = store.create_conversation(request.worker_id, request.transcript, request.conversation_id)
    background_tasks.add_task(run_extraction_pipeline, conversation.id)
    return ConversationIngestResponse(
        conversation_id=conversation.id,
        status="processing",
        message="Transcript queued for extraction",
    )


@router.get("/{conversation_id}/status", response_model=ConversationStatusResponse)
async def conversation_status(conversation_id: str):
    conversation = store.conversations.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationStatusResponse(
        conversation_id=conversation.id,
        status=conversation.extraction_status.value,
        extracted_count=conversation.extracted_count,
        quarantined_count=conversation.quarantined_count,
        skipped_count=conversation.skipped_count,
        raw_extractions=conversation.raw_extractions,
    )

