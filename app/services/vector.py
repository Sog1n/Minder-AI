from __future__ import annotations

import math
from typing import Protocol

from app.core.config import settings
from app.core.store import store
from app.models.domain import KnowledgeItem, KnowledgeStatus, SopDocument
from app.services.llm import openai_enabled
from app.services.text import lexical_similarity


class VectorSearch(Protocol):
    async def index_knowledge_item(self, item: KnowledgeItem) -> None:
        ...

    async def index_sop_document(self, doc: SopDocument) -> None:
        ...

    async def search_knowledge(self, query: str, limit: int = 5) -> list[tuple[str, float]]:
        ...

    async def search_sop(self, query: str, limit: int = 3) -> list[tuple[str, float]]:
        ...


def item_text(item: KnowledgeItem) -> str:
    fact = item.structured_fact
    return (
        f"Entity: {fact.get('entity')}. Attribute: {fact.get('attribute')}. "
        f"Value: {fact.get('value')} {fact.get('unit', '')}. Condition: {fact.get('condition')}. "
        f"Domain: {fact.get('domain')}. Original: {item.raw_text}"
    )


def sop_text(doc: SopDocument) -> str:
    return (
        f"Entity: {doc.entity}. Attribute: {doc.attribute}. Value: {doc.value} {doc.unit or ''}. "
        f"Condition: {doc.condition}. Domain: {doc.domain}. SOP: {doc.text}"
    )


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class LexicalVectorSearch:
    async def index_knowledge_item(self, item: KnowledgeItem) -> None:
        return None

    async def index_sop_document(self, doc: SopDocument) -> None:
        return None

    async def search_knowledge(self, query: str, limit: int = 5) -> list[tuple[str, float]]:
        scored = []
        for item in store.knowledge_items.values():
            if item.status == KnowledgeStatus.VERIFIED:
                scored.append((item.id, lexical_similarity(query, item_text(item))))
        return [(item_id, score) for item_id, score in sorted(scored, key=lambda row: row[1], reverse=True)[:limit] if score > 0]

    async def search_sop(self, query: str, limit: int = 3) -> list[tuple[str, float]]:
        scored = [
            (doc.chunk_id, lexical_similarity(query + " " + doc.entity + " " + doc.attribute, sop_text(doc)))
            for doc in store.sop_documents.values()
        ]
        return [(chunk_id, score) for chunk_id, score in sorted(scored, key=lambda row: row[1], reverse=True)[:limit] if score > 0]


class OpenAIEmbeddingSearch:
    async def embed(self, text: str) -> list[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(model=settings.openai_embedding_model, input=text)
        return response.data[0].embedding

    async def index_knowledge_item(self, item: KnowledgeItem) -> None:
        store.knowledge_vectors[item.id] = await self.embed(item_text(item))

    async def index_sop_document(self, doc: SopDocument) -> None:
        store.sop_vectors[doc.chunk_id] = await self.embed(sop_text(doc))

    async def ensure_indexes(self) -> None:
        for doc in store.sop_documents.values():
            if doc.chunk_id not in store.sop_vectors:
                await self.index_sop_document(doc)
        for item in store.knowledge_items.values():
            if item.status == KnowledgeStatus.VERIFIED and item.id not in store.knowledge_vectors:
                await self.index_knowledge_item(item)

    async def search_knowledge(self, query: str, limit: int = 5) -> list[tuple[str, float]]:
        await self.ensure_indexes()
        query_vector = await self.embed(query)
        scored = [
            (item_id, cosine(query_vector, vector))
            for item_id, vector in store.knowledge_vectors.items()
            if store.knowledge_items.get(item_id) and store.knowledge_items[item_id].status == KnowledgeStatus.VERIFIED
        ]
        return sorted(scored, key=lambda row: row[1], reverse=True)[:limit]

    async def search_sop(self, query: str, limit: int = 3) -> list[tuple[str, float]]:
        await self.ensure_indexes()
        query_vector = await self.embed(query)
        scored = [(chunk_id, cosine(query_vector, vector)) for chunk_id, vector in store.sop_vectors.items()]
        return sorted(scored, key=lambda row: row[1], reverse=True)[:limit]


def get_vector_search() -> VectorSearch:
    return OpenAIEmbeddingSearch() if openai_enabled() else LexicalVectorSearch()

