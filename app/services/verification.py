from __future__ import annotations

from dataclasses import dataclass
from math import log

from app.core.store import store
from app.models.domain import KnowledgeItem, KnowledgeStatus, RelationType
from app.services.llm import get_conflict_judge
from app.services.text import normalize_value, numeric_value


@dataclass
class SopConflict:
    sop_chunk_id: str
    sop_value: str
    sop_condition: str | None
    similarity_score: float
    conflict_reason: str


def same_condition(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return left == right


def values_conflict(left: str, right: str) -> bool:
    left_num = numeric_value(left)
    right_num = numeric_value(right)
    if left_num is not None and right_num is not None:
        return abs(left_num - right_num) > 0.01
    return normalize_value(left) != normalize_value(right)


def values_support(left: str, right: str) -> bool:
    return not values_conflict(left, right)


def find_sop_conflict(item: KnowledgeItem) -> SopConflict | None:
    fact = item.structured_fact
    for sop in store.sop_documents.values():
        if sop.entity != fact.get("entity") or sop.attribute != fact.get("attribute"):
            continue
        if same_condition(str(fact.get("condition", "")), sop.condition) and values_conflict(
            str(fact.get("value", "")), sop.value
        ):
            return SopConflict(
                sop_chunk_id=sop.chunk_id,
                sop_value=sop.value,
                sop_condition=sop.condition,
                similarity_score=1.0,
                conflict_reason="Same entity/attribute as SOP but value differs.",
            )
    return None


def related_worker_items(item: KnowledgeItem) -> list[KnowledgeItem]:
    fact = item.structured_fact
    related: list[KnowledgeItem] = []
    for existing in store.knowledge_items.values():
        if existing.id == item.id:
            continue
        if existing.status not in {
            KnowledgeStatus.VERIFIED,
            KnowledgeStatus.QUARANTINED,
            KnowledgeStatus.ESCALATED,
        }:
            continue
        if (
            existing.structured_fact.get("entity") == fact.get("entity")
            and existing.structured_fact.get("attribute") == fact.get("attribute")
        ):
            related.append(existing)
    return related


def compute_trust_weight(item: KnowledgeItem) -> float:
    weight = item.confidence_score
    weight += log(1 + item.support_count) * 0.3
    weight -= item.contradiction_count * 0.15
    source_weights = {
        "WORKER_CORRECTION": 0.20,
        "WORKER_TEACHING": 0.10,
        "WORKER_WARNING": 0.10,
        "AMBIGUOUS": -0.10,
    }
    weight += source_weights.get(str(item.source_type), 0)
    return max(0.0, weight)


def auto_accept(item: KnowledgeItem, note: str = "Auto-accepted by verification pipeline.") -> KnowledgeItem:
    can_auto_accept = (
        item.confidence_score >= 0.70
        and item.noise_score <= 0.35
        and item.contradiction_count == 0
        and item.structured_fact.get("domain") != "safety"
    )
    if can_auto_accept:
        return store.update_status(item, KnowledgeStatus.VERIFIED, note)
    return store.update_status(item, KnowledgeStatus.QUARANTINED, "Confidence below auto-accept threshold.")


def handle_supporting_evidence(new_item: KnowledgeItem, existing_item: KnowledgeItem) -> KnowledgeItem:
    if new_item.worker_id == existing_item.worker_id:
        return store.update_status(new_item, KnowledgeStatus.REJECTED, "Duplicate support from original worker.")
    inserted = store.add_support(existing_item.id, str(new_item.worker_id), new_item.id)
    if not inserted:
        return store.update_status(new_item, KnowledgeStatus.REJECTED, "Duplicate support from same worker.")
    existing_item.support_count += 1
    existing_item.confidence_score = min(existing_item.confidence_score + 0.05, 1.0)
    if existing_item.worker_id and existing_item.worker_id in store.workers:
        worker = store.workers[existing_item.worker_id]
        worker.trust_score = min(worker.trust_score + 0.02, 1.0)
    store.add_relation(new_item.id, existing_item.id, RelationType.SUPPORTS, 1.0)
    distinct_supporters = store.support_worker_count(existing_item.id)
    if (
        existing_item.status == KnowledgeStatus.QUARANTINED
        and distinct_supporters >= 2
        and existing_item.contradiction_count == 0
    ):
        auto_accept(existing_item, "Promoted after confirmation from two distinct workers.")
    return store.update_status(new_item, KnowledgeStatus.REJECTED, "Duplicate; support_count incremented on existing item.")


def resolve_worker_conflict(new_item: KnowledgeItem, existing_item: KnowledgeItem) -> KnowledgeItem:
    new_item.contradiction_count += 1
    existing_item.contradiction_count += 1
    store.add_relation(new_item.id, existing_item.id, RelationType.CONTRADICTS, 1.0)

    if new_item.structured_fact.get("domain") == "safety":
        return store.update_status(new_item, KnowledgeStatus.ESCALATED, "Safety-critical claim requires human review.")

    new_weight = compute_trust_weight(new_item)
    old_weight = compute_trust_weight(existing_item)
    if new_weight > old_weight * 1.5:
        store.add_relation(new_item.id, existing_item.id, RelationType.SUPERSEDES, 1.0)
        store.update_status(existing_item, KnowledgeStatus.SUPERSEDED, "Superseded by higher-confidence item.")
        return auto_accept(new_item, "New higher-confidence item superseded old item.")
    if old_weight > new_weight * 1.5:
        return store.update_status(new_item, KnowledgeStatus.REJECTED, "Contradicts higher-confidence existing knowledge.")

    store.update_status(existing_item, KnowledgeStatus.QUARANTINED, "Under conflict review.")
    return store.update_status(new_item, KnowledgeStatus.QUARANTINED, "Contradicts existing knowledge.")


async def run_verification_pipeline(item_id: str) -> KnowledgeItem:
    item = store.knowledge_items[item_id]
    if item.status != KnowledgeStatus.PENDING:
        return item

    sop_conflict = find_sop_conflict(item)
    if sop_conflict:
        return store.update_status(
            item,
            KnowledgeStatus.ESCALATED,
            "Contradicts official SOP seeded stub.",
            metadata=sop_conflict.__dict__,
        )

    if item.structured_fact.get("domain") == "safety":
        return store.update_status(item, KnowledgeStatus.ESCALATED, "Safety-critical claim requires human review.")

    judge = get_conflict_judge()
    for existing in related_worker_items(item):
        judgment = await judge.judge(existing.structured_fact, item.structured_fact)
        if not judgment.is_contradiction:
            return handle_supporting_evidence(item, existing)
        if judgment.recommended_action == "ESCALATE":
            return store.update_status(
                item,
                KnowledgeStatus.ESCALATED,
                f"LLM judge escalated conflict: {judgment.explanation}",
                metadata=judgment.model_dump(),
            )
        if judgment.contradiction_type == "DIRECT":
            return resolve_worker_conflict(item, existing)

    return auto_accept(item)
