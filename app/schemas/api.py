from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.domain import KnowledgeStatus, SourceType


class ConversationIngestRequest(BaseModel):
    worker_id: str
    transcript: str = Field(min_length=1)
    conversation_id: str | None = None


class ConversationIngestResponse(BaseModel):
    conversation_id: str
    status: str
    message: str


class ConversationStatusResponse(BaseModel):
    conversation_id: str
    status: str
    extracted_count: int
    quarantined_count: int
    skipped_count: int
    raw_extractions: list[dict[str, Any]]


class WorkerCreateRequest(BaseModel):
    id: str
    name: str
    department: str
    seniority_years: int = 0
    trust_score: float = 0.5


class KnowledgeResolveRequest(BaseModel):
    decision: Literal["VERIFY", "REJECT", "SUPERSEDE", "QUARANTINE"]
    note: str = ""
    supervisor_id: str
    applies_to_conflict_id: str | None = None


class KnowledgeSource(BaseModel):
    id: str
    type: Literal["SOP", "TRIBAL"]
    text: str
    score: float
    status: str | None = None


class AgentQueryRequest(BaseModel):
    worker_id: str
    query: str = Field(min_length=1)
    conversation_id: str | None = None


class AgentQueryResponse(BaseModel):
    response: str
    sources: list[KnowledgeSource]
    retrieval_latency_ms: int
    generation_latency_ms: int
    latency_ms: int
    used_tribal_knowledge: bool
    query_log_id: str


class AgentCorrectionRequest(BaseModel):
    correction_text: str = Field(min_length=1)
    worker_id: str


class AgentCorrectionResponse(BaseModel):
    query_log_id: str
    conversation_id: str
    status: str


class ExtractedFact(BaseModel):
    raw_text: str
    structured_fact: dict[str, Any]
    source_type: SourceType
    is_likely_noise: bool = False
    noise_reason: str = ""
    llm_confidence: float = 0.5
    requires_verification: bool = True


class KnowledgeListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int


class ConflictListResponse(BaseModel):
    conflicts: list[dict[str, Any]]


class SeedResponse(BaseModel):
    workers: int
    sop_documents: int

