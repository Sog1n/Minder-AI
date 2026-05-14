from __future__ import annotations

from time import perf_counter

from app.core.store import new_id, public_dict, store
from app.core.config import settings
from app.models.domain import AgentQueryLog, KnowledgeStatus
from app.schemas.api import AgentQueryResponse, KnowledgeSource
from app.services.llm import openai_enabled
from app.services.verification import values_conflict
from app.services.vector import get_vector_search


async def sop_sources(query: str) -> list[tuple[str, float]]:
    return await get_vector_search().search_sop(query, limit=3)


async def tribal_sources(query: str) -> list[tuple[str, float]]:
    return await get_vector_search().search_knowledge(query, limit=5)


def find_sop_tribal_conflict(sop_ids: list[str], tribal_ids: list[str]) -> tuple[str, str] | None:
    for sop_id in sop_ids:
        sop = store.sop_documents[sop_id]
        for item_id in tribal_ids:
            item = store.knowledge_items[item_id]
            if sop.entity == item.structured_fact.get("entity") and sop.attribute == item.structured_fact.get("attribute"):
                if values_conflict(sop.value, str(item.structured_fact.get("value", ""))):
                    return sop_id, item_id
    return None


def compose_template_answer(query: str, sop_ids: list[str], tribal_ids: list[str]) -> str:
    conflict = find_sop_tribal_conflict(sop_ids, tribal_ids)
    if conflict:
        sop = store.sop_documents[conflict[0]]
        item = store.knowledge_items[conflict[1]]
        return (
            f"Follow SOP: {sop.text} "
            f"A verified field claim says {item.structured_fact.get('value')} "
            "for the same item, so treat that claim as supervisor-review material."
        )
    if sop_ids:
        sop_lines = [store.sop_documents[sop_id].text for sop_id in sop_ids[:2]]
        answer = " ".join(sop_lines)
        if tribal_ids:
            tribal = store.knowledge_items[tribal_ids[0]]
            answer += f" Field note: {tribal.raw_text}"
        return answer
    if tribal_ids:
        tribal = store.knowledge_items[tribal_ids[0]]
        return f"Based on verified field knowledge: {tribal.raw_text}"
    return "I'm not certain. Please verify with a supervisor."


async def compose_llm_answer(query: str, sop_ids: list[str], tribal_ids: list[str]) -> str:
    from openai import AsyncOpenAI

    sop_context = "\n".join(f"- {store.sop_documents[sop_id].text}" for sop_id in sop_ids) or "No SOP match."
    tribal_context = "\n".join(
        f"- {store.knowledge_items[item_id].raw_text} | fact={store.knowledge_items[item_id].structured_fact}"
        for item_id in tribal_ids
    ) or "No verified tribal knowledge match."
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=settings.openai_chat_model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are Minder, a voice-first AI co-worker for factory workers. "
                    "Answer briefly and actionably. SOP documents are official and must be the default answer. "
                    "Verified tribal knowledge can augment SOP, but it must not override SOP. "
                    "If verified tribal knowledge conflicts with SOP, answer according to SOP and mention that the field claim needs supervisor review. "
                    "Never invent specific numbers, timings, temperatures, or settings."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Worker query:\n{query}\n\n"
                    f"SOP reference:\n{sop_context}\n\n"
                    f"Verified tribal knowledge:\n{tribal_context}"
                ),
            },
        ],
    )
    return response.output_text


async def compose_answer(query: str, sop_ids: list[str], tribal_ids: list[str]) -> str:
    if openai_enabled():
        return await compose_llm_answer(query, sop_ids, tribal_ids)
    return compose_template_answer(query, sop_ids, tribal_ids)


async def answer_query(worker_id: str, query: str, conversation_id: str | None = None) -> AgentQueryResponse:
    total_start = perf_counter()
    log = store.add_query_log(AgentQueryLog(id=new_id(), worker_id=worker_id, query_text=query))

    retrieval_start = perf_counter()
    sop_ranked = await sop_sources(query)
    tribal_ranked = await tribal_sources(query)
    retrieval_ms = int((perf_counter() - retrieval_start) * 1000)

    used_sop_ids = [chunk_id for chunk_id, _ in sop_ranked]
    used_tribal_ids = [item_id for item_id, score in tribal_ranked if score >= 0.05]
    store.log_retrievals(log.id, [(item_id, score) for item_id, score in tribal_ranked if item_id in used_tribal_ids])

    generation_start = perf_counter()
    response = await compose_answer(query, used_sop_ids, used_tribal_ids)
    generation_ms = int((perf_counter() - generation_start) * 1000)

    log.response_text = response
    log.used_sop_chunks = used_sop_ids
    log.used_knowledge_ids = used_tribal_ids
    log.retrieval_latency_ms = retrieval_ms
    log.generation_latency_ms = generation_ms
    log.latency_ms = int((perf_counter() - total_start) * 1000)

    sources: list[KnowledgeSource] = []
    for chunk_id, score in sop_ranked:
        sop = store.sop_documents[chunk_id]
        sources.append(KnowledgeSource(id=chunk_id, type="SOP", text=sop.text, score=round(score, 3)))
    for item_id, score in tribal_ranked:
        item = store.knowledge_items[item_id]
        sources.append(
            KnowledgeSource(
                id=item_id,
                type="TRIBAL",
                text=item.raw_text,
                score=round(score, 3),
                status=item.status,
            )
        )

    return AgentQueryResponse(
        response=response,
        sources=sources,
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=generation_ms,
        latency_ms=log.latency_ms,
        used_tribal_knowledge=bool(used_tribal_ids),
        query_log_id=log.id,
    )


def query_log_public(log_id: str) -> dict:
    return public_dict(store.query_logs[log_id])
