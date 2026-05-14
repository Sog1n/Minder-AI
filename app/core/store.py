from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from app.models.domain import (
    AgentQueryLog,
    AuditLog,
    Conversation,
    ExtractionStatus,
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeStatus,
    RelationType,
    RetrievalEvent,
    SopDocument,
    SourceType,
    SupportEvidence,
    Worker,
)


def new_id() -> str:
    return str(uuid4())


def public_dict(value: Any) -> Any:
    if is_dataclass(value):
        data = asdict(value)
    elif isinstance(value, dict):
        data = dict(value)
    else:
        return value
    for key, item in list(data.items()):
        if isinstance(item, datetime):
            data[key] = item.isoformat() + "Z"
    return data


class DemoStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self.workers: dict[str, Worker] = {}
        self.conversations: dict[str, Conversation] = {}
        self.knowledge_items: dict[str, KnowledgeItem] = {}
        self.relations: dict[str, KnowledgeRelation] = {}
        self.sop_documents: dict[str, SopDocument] = {}
        self.query_logs: dict[str, AgentQueryLog] = {}
        self.retrieval_events: dict[str, RetrievalEvent] = {}
        self.audit_logs: dict[str, AuditLog] = {}
        self.support_evidence: dict[str, SupportEvidence] = {}
        self.knowledge_vectors: dict[str, list[float]] = {}
        self.sop_vectors: dict[str, list[float]] = {}

    def reset(self) -> None:
        with self._lock:
            self.workers.clear()
            self.conversations.clear()
            self.knowledge_items.clear()
            self.relations.clear()
            self.sop_documents.clear()
            self.query_logs.clear()
            self.retrieval_events.clear()
            self.audit_logs.clear()
            self.support_evidence.clear()
            self.knowledge_vectors.clear()
            self.sop_vectors.clear()

    def seed_defaults(self) -> None:
        with self._lock:
            if not self.workers:
                self.add_worker("maria", "Maria", "laundry", 10, 0.78)
                self.add_worker("carlos", "Carlos", "welding", 8, 0.74)
                self.add_worker("worker_a", "Worker A", "laundry", 5, 0.62)
                self.add_worker("worker_b", "Worker B", "laundry", 3, 0.60)
                self.add_worker("new_hire", "New Hire", "general", 0, 0.35)
            if not self.sop_documents:
                self.seed_sop_documents()

    def add_worker(
        self,
        worker_id: str,
        name: str,
        department: str,
        seniority_years: int,
        trust_score: float,
    ) -> Worker:
        worker = Worker(
            id=worker_id,
            name=name,
            department=department,
            seniority_years=seniority_years,
            trust_score=trust_score,
        )
        self.workers[worker.id] = worker
        return worker

    def seed_sop_documents(self) -> list[SopDocument]:
        docs = [
            SopDocument(
                chunk_id="sop_dryer_station_2_temp",
                doc_id="sop_laundry_001",
                section="Dryer settings",
                text="Dryer at station 2 should run at 78 degrees Celsius for the standard cycle.",
                domain="laundry",
                entity="dryer_station_2",
                attribute="temperature",
                value="78",
                unit="celsius",
                condition="standard_cycle",
            ),
            SopDocument(
                chunk_id="sop_hotel_a_polyester",
                doc_id="sop_laundry_002",
                section="Hotel A sorting",
                text="Hotel A polyester should be separated from cotton before washing.",
                domain="laundry",
                entity="hotel_a_polyester",
                attribute="sorting_rule",
                value="separate_from_cotton",
                condition="all_cycles",
            ),
            SopDocument(
                chunk_id="sop_station_3_current",
                doc_id="sop_welding_001",
                section="Station 3 current",
                text="Station 3 welding current should follow the baseline current unless supervisor approves a change.",
                domain="welding",
                entity="station_3",
                attribute="current_adjustment",
                value="0",
                unit="percent",
                condition="standard_operation",
            ),
            SopDocument(
                chunk_id="sop_safety_guard",
                doc_id="sop_safety_001",
                section="Machine guards",
                text="Never bypass a machine guard. Stop the line and notify a supervisor.",
                domain="safety",
                entity="machine_guard",
                attribute="bypass_policy",
                value="never_bypass",
                condition="all_operations",
            ),
            SopDocument(
                chunk_id="sop_cotton_dryer",
                doc_id="sop_laundry_003",
                section="Cotton dryer settings",
                text="Cotton loads run at 80 degrees Celsius on the standard dryer cycle.",
                domain="laundry",
                entity="cotton_load",
                attribute="temperature",
                value="80",
                unit="celsius",
                condition="standard_cycle",
            ),
        ]
        for doc in docs:
            self.sop_documents[doc.chunk_id] = doc
        return docs

    def create_conversation(self, worker_id: str, transcript: str, conversation_id: str | None = None) -> Conversation:
        conversation = Conversation(id=conversation_id or new_id(), worker_id=worker_id, transcript=transcript)
        with self._lock:
            self.conversations[conversation.id] = conversation
        return conversation

    def add_knowledge_item(self, item: KnowledgeItem) -> KnowledgeItem:
        with self._lock:
            self.knowledge_items[item.id] = item
        return item

    def update_status(
        self,
        item: KnowledgeItem,
        status: KnowledgeStatus,
        note: str,
        actor_type: str = "SYSTEM",
        actor_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeItem:
        previous = item.status
        item.status = status
        item.updated_at = datetime.now(UTC)
        item.resolution_note = note
        if status == KnowledgeStatus.VERIFIED:
            item.verified_at = item.updated_at
        self.add_audit(item.id, actor_type, f"STATUS_{status}", actor_id, previous, status, note, metadata or {})
        return item

    def add_audit(
        self,
        knowledge_item_id: str,
        actor_type: str,
        action: str,
        actor_id: str | None,
        from_status: KnowledgeStatus | str | None,
        to_status: KnowledgeStatus | str | None,
        note: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            id=new_id(),
            knowledge_item_id=knowledge_item_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            from_status=str(from_status) if from_status else None,
            to_status=str(to_status) if to_status else None,
            note=note,
            metadata=metadata or {},
        )
        with self._lock:
            self.audit_logs[audit.id] = audit
        return audit

    def add_relation(self, source_id: str, target_id: str, relation_type: RelationType, score: float | None = None) -> None:
        existing = [
            rel
            for rel in self.relations.values()
            if rel.source_id == source_id and rel.target_id == target_id and rel.relation_type == relation_type
        ]
        if existing:
            return
        relation = KnowledgeRelation(new_id(), source_id, target_id, relation_type, score)
        self.relations[relation.id] = relation

    def add_support(self, knowledge_item_id: str, worker_id: str, supporting_item_id: str | None) -> bool:
        if any(ev.knowledge_item_id == knowledge_item_id and ev.worker_id == worker_id for ev in self.support_evidence.values()):
            return False
        ev = SupportEvidence(new_id(), knowledge_item_id, worker_id, supporting_item_id)
        self.support_evidence[ev.id] = ev
        return True

    def support_worker_count(self, knowledge_item_id: str) -> int:
        return len({ev.worker_id for ev in self.support_evidence.values() if ev.knowledge_item_id == knowledge_item_id})

    def add_query_log(self, log: AgentQueryLog) -> AgentQueryLog:
        self.query_logs[log.id] = log
        return log

    def log_retrievals(self, query_log_id: str, scored_items: list[tuple[str, float]]) -> None:
        for index, (item_id, score) in enumerate(scored_items, start=1):
            event = RetrievalEvent(new_id(), query_log_id, item_id, score, index)
            self.retrieval_events[event.id] = event

    def metric_dashboard(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        since_7d = now - timedelta(days=7)
        items = list(self.knowledge_items.values())
        logs = list(self.query_logs.values())
        verified_items = [i for i in items if i.status == KnowledgeStatus.VERIFIED]
        retrieved_7d = {
            ev.knowledge_item_id
            for ev in self.retrieval_events.values()
            if ev.created_at >= since_7d and self.knowledge_items.get(ev.knowledge_item_id, None)
        }
        total_queries = len(logs)
        corrections = sum(1 for log in logs if log.was_corrected)
        queries_with_tribal = sum(1 for log in logs if log.used_knowledge_ids)
        rejected = sum(1 for i in items if i.status == KnowledgeStatus.REJECTED)
        verified = len(verified_items)
        status_counts = {status.value: sum(1 for i in items if i.status == status) for status in KnowledgeStatus}
        domains: dict[str, list[float]] = {}
        for item in items:
            domain = str(item.structured_fact.get("domain", "unknown"))
            domains.setdefault(domain, []).append(item.confidence_score)

        top_domains = [
            {"domain": domain, "count": len(scores), "avg_confidence": round(sum(scores) / len(scores), 3)}
            for domain, scores in sorted(domains.items(), key=lambda entry: len(entry[1]), reverse=True)
        ]
        return {
            "today": {
                "total_knowledge_items": len(items),
                "verified_count": verified,
                "quarantined_count": status_counts[KnowledgeStatus.QUARANTINED],
                "escalated_count": status_counts[KnowledgeStatus.ESCALATED],
                "pending_count": status_counts[KnowledgeStatus.PENDING],
                "rejected_count": rejected,
                "superseded_count": status_counts[KnowledgeStatus.SUPERSEDED],
                "total_queries": total_queries,
                "correction_rate": corrections / total_queries if total_queries else 0,
                "kbc_score": queries_with_tribal / total_queries if total_queries else 0,
                "kar": verified / (verified + rejected) if (verified + rejected) else 0,
                "kur": len(retrieved_7d & {i.id for i in verified_items}) / verified if verified else 0,
                "avg_confidence_score": (
                    sum(i.confidence_score for i in verified_items) / verified if verified else 0
                ),
            },
            "trend_7d": [],
            "top_domains": top_domains,
            "pending_review": {
                "quarantined_count": status_counts[KnowledgeStatus.QUARANTINED],
                "escalated_count": status_counts[KnowledgeStatus.ESCALATED],
            },
            "status_counts": status_counts,
        }


store = DemoStore()
