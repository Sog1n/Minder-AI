from __future__ import annotations

import re
from typing import Any

from app.core.store import new_id, store
from app.models.domain import ExtractionStatus, KnowledgeItem, KnowledgeStatus, SourceType, Worker
from app.services.llm import KnowledgeExtractor, OpenAIExtractor, openai_enabled


def infer_source_type(text: str) -> SourceType:
    lowered = text.lower()
    if any(term in lowered for term in ["wrong", "actually", "not enough", "keeps telling", "no,"]):
        return SourceType.WORKER_CORRECTION
    if any(term in lowered for term in ["must", "never", "warning", "danger", "safety"]):
        return SourceType.WORKER_WARNING
    if any(term in lowered for term in ["always", "should", "i use", "i drop"]):
        return SourceType.WORKER_TEACHING
    return SourceType.AMBIGUOUS


class DemoExtractor:
    async def extract(self, transcript: str, worker: Worker) -> list[dict[str, Any]]:
        return demo_extract_facts(transcript, worker)


def get_extractor() -> KnowledgeExtractor:
    return OpenAIExtractor() if openai_enabled() else DemoExtractor()


def demo_extract_facts(transcript: str, worker: Worker) -> list[dict[str, Any]]:
    text = transcript.strip()
    lowered = text.lower()
    facts: list[dict[str, Any]] = []

    dryer_match = re.search(r"dryer(?: at)? station\s*(\d+).*?(\d+(?:\.\d+)?)\s*(?:degrees|degree|c|celsius)", lowered)
    if dryer_match:
        station, value = dryer_match.groups()
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": f"dryer_station_{station}",
                    "attribute": "temperature",
                    "value": value,
                    "unit": "celsius",
                    "condition": "standard_cycle",
                    "domain": "laundry",
                },
                "source_type": infer_source_type(text),
                "is_likely_noise": False,
                "noise_reason": "",
                "llm_confidence": 0.72,
                "requires_verification": True,
            }
        )

    current_match = re.search(r"station\s*(\d+).*?(?:drop|lower|reduce).*?current.*?(\d+(?:\.\d+)?)\s*%", lowered)
    if current_match:
        station, value = current_match.groups()
        condition = "after_lunch_tuesdays" if "tuesday" in lowered and "lunch" in lowered else "operator_observed"
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": f"station_{station}",
                    "attribute": "current_adjustment",
                    "value": f"-{value}",
                    "unit": "percent",
                    "condition": condition,
                    "domain": "welding",
                },
                "source_type": infer_source_type(text),
                "is_likely_noise": False,
                "noise_reason": "",
                "llm_confidence": 0.78,
                "requires_verification": True,
            }
        )

    if "hotel a" in lowered and "polyester" in lowered and "cotton" in lowered and any(
        term in lowered for term in ["separate", "mixed", "shrinks", "ruin"]
    ):
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": "hotel_a_polyester",
                    "attribute": "sorting_rule",
                    "value": "separate_from_cotton",
                    "unit": "",
                    "condition": "all_cycles",
                    "domain": "laundry",
                },
                "source_type": infer_source_type(text),
                "is_likely_noise": False,
                "noise_reason": "",
                "llm_confidence": 0.82,
                "requires_verification": True,
            }
        )

    if any(term in lowered for term in ["machine guard", "bypass guard", "safety"]):
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": "machine_guard",
                    "attribute": "bypass_policy",
                    "value": "requires_supervisor_review",
                    "unit": "",
                    "condition": "all_operations",
                    "domain": "safety",
                },
                "source_type": infer_source_type(text),
                "is_likely_noise": False,
                "noise_reason": "",
                "llm_confidence": 0.68,
                "requires_verification": True,
            }
        )

    if not facts and any(term in lowered for term in ["always", "should", "must", "never"]):
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": "unknown",
                    "attribute": "operator_note",
                    "value": text[:160],
                    "unit": "",
                    "condition": "unspecified",
                    "domain": worker.department or "general",
                },
                "source_type": infer_source_type(text),
                "is_likely_noise": True,
                "noise_reason": "Could not extract concrete entity/attribute/value.",
                "llm_confidence": 0.36,
                "requires_verification": True,
            }
        )

    if not facts and any(term in lowered for term in ["haha", "lol", "hopes and dreams", "just guessing"]):
        facts.append(
            {
                "raw_text": text,
                "structured_fact": {
                    "entity": "unknown",
                    "attribute": "noise",
                    "value": text[:160],
                    "domain": "general",
                },
                "source_type": SourceType.AMBIGUOUS,
                "is_likely_noise": True,
                "noise_reason": "Humor or explicit guessing.",
                "llm_confidence": 0.2,
                "requires_verification": False,
            }
        )

    return facts[:5]


def compute_noise_score(extraction: dict[str, Any], worker: Worker) -> float:
    score = 0.0
    if extraction.get("is_likely_noise"):
        score += 0.50
    confidence = float(extraction.get("llm_confidence", 0.5))
    if confidence < 0.4:
        score += 0.30
    elif confidence < 0.6:
        score += 0.10
    if extraction.get("source_type") == SourceType.AMBIGUOUS:
        score += 0.20
    value = str(extraction["structured_fact"].get("value", ""))
    if not any(char.isdigit() for char in value) and len(value.split()) > 5:
        score += 0.15
    if worker.seniority_years < 1 and extraction["structured_fact"].get("domain") == "safety":
        score += 0.20
    return min(score, 1.0)


def compute_confidence_score(extraction: dict[str, Any], worker: Worker) -> float:
    score = float(extraction.get("llm_confidence", 0.5))
    score += min(worker.seniority_years / 20, 1.0) * 0.2
    score = score * 0.7 + worker.trust_score * 0.3
    source_bonuses = {
        SourceType.WORKER_CORRECTION: 0.10,
        SourceType.WORKER_TEACHING: 0.05,
        SourceType.WORKER_WARNING: 0.05,
        SourceType.AMBIGUOUS: -0.10,
    }
    source_type = extraction.get("source_type", SourceType.AMBIGUOUS)
    score += source_bonuses.get(source_type, 0)
    return max(0.0, min(score, 1.0))


async def run_extraction_pipeline(conversation_id: str) -> None:
    conversation = store.conversations[conversation_id]
    worker = store.workers[conversation.worker_id]
    conversation.extraction_status = ExtractionStatus.PROCESSING
    extractor = get_extractor()
    try:
        extractions = await extractor.extract(conversation.transcript, worker)
    except Exception as exc:
        conversation.extraction_status = ExtractionStatus.FAILED
        conversation.raw_extractions = [{"error": str(exc), "extractor": extractor.__class__.__name__}]
        return
    conversation.raw_extractions = extractions

    from app.services.verification import run_verification_pipeline

    pending_item_ids: list[str] = []
    skipped = 0
    quarantined = 0
    for extraction in extractions:
        noise_score = compute_noise_score(extraction, worker)
        if noise_score > 0.65:
            skipped += 1
            continue
        status = KnowledgeStatus.QUARANTINED if noise_score > 0.35 else KnowledgeStatus.PENDING
        if status == KnowledgeStatus.QUARANTINED:
            quarantined += 1
        item = KnowledgeItem(
            id=new_id(),
            raw_text=extraction["raw_text"],
            structured_fact=extraction["structured_fact"],
            conversation_id=conversation.id,
            worker_id=worker.id,
            source_type=extraction.get("source_type", SourceType.AMBIGUOUS),
            status=status,
            confidence_score=compute_confidence_score(extraction, worker),
            noise_score=noise_score,
            qdrant_vector_id=new_id(),
        )
        store.add_knowledge_item(item)
        store.add_audit(
            item.id,
            "SYSTEM",
            "CREATE_KNOWLEDGE_ITEM",
            None,
            None,
            item.status,
            "Created from extraction pipeline.",
            {"conversation_id": conversation.id},
        )
        if item.status == KnowledgeStatus.PENDING:
            pending_item_ids.append(item.id)

    conversation.extracted_count = len(extractions) - skipped
    conversation.quarantined_count = quarantined
    conversation.skipped_count = skipped
    conversation.extraction_status = ExtractionStatus.DONE
    for item_id in pending_item_ids:
        await run_verification_pipeline(item_id)
