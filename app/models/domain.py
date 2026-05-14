from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class SourceType(StrEnum):
    WORKER_CORRECTION = "WORKER_CORRECTION"
    WORKER_TEACHING = "WORKER_TEACHING"
    WORKER_WARNING = "WORKER_WARNING"
    AMBIGUOUS = "AMBIGUOUS"


class KnowledgeStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    QUARANTINED = "QUARANTINED"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class RelationType(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    REFINES = "REFINES"


@dataclass
class Worker:
    id: str
    name: str
    department: str
    seniority_years: int = 0
    trust_score: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Conversation:
    id: str
    worker_id: str
    transcript: str
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    raw_extractions: list[dict[str, Any]] = field(default_factory=list)
    processed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    extracted_count: int = 0
    quarantined_count: int = 0
    skipped_count: int = 0


@dataclass
class KnowledgeItem:
    id: str
    raw_text: str
    structured_fact: dict[str, Any]
    conversation_id: str | None
    worker_id: str | None
    source_type: SourceType
    status: KnowledgeStatus = KnowledgeStatus.PENDING
    confidence_score: float = 0.5
    noise_score: float = 0.0
    support_count: int = 1
    contradiction_count: int = 0
    qdrant_vector_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified_at: datetime | None = None
    resolution_note: str | None = None


@dataclass
class KnowledgeRelation:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    similarity_score: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SopDocument:
    chunk_id: str
    doc_id: str
    text: str
    domain: str
    entity: str
    attribute: str
    value: str
    unit: str | None = None
    condition: str | None = None
    section: str | None = None


@dataclass
class AgentQueryLog:
    id: str
    worker_id: str | None
    query_text: str
    response_text: str = ""
    used_knowledge_ids: list[str] = field(default_factory=list)
    used_sop_chunks: list[str] = field(default_factory=list)
    was_corrected: bool = False
    correction_text: str | None = None
    retrieval_latency_ms: int = 0
    generation_latency_ms: int = 0
    latency_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RetrievalEvent:
    id: str
    query_log_id: str
    knowledge_item_id: str
    similarity_score: float
    rank_position: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AuditLog:
    id: str
    knowledge_item_id: str
    actor_type: str
    action: str
    actor_id: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SupportEvidence:
    id: str
    knowledge_item_id: str
    worker_id: str
    supporting_item_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
