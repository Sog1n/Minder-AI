from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.domain import SourceType, Worker


class StructuredFact(BaseModel):
    entity: str = Field(description="Canonical machine, product, station, or process identifier.")
    attribute: str = Field(description="The operational attribute being claimed.")
    value: str = Field(description="Concrete value, rule, setting, or behavior.")
    unit: str = ""
    condition: str = "unspecified"
    domain: str = "general"


class LLMExtraction(BaseModel):
    raw_text: str
    structured_fact: StructuredFact
    source_type: SourceType
    is_likely_noise: bool = False
    noise_reason: str = ""
    llm_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    requires_verification: bool = True


class ExtractionResponse(BaseModel):
    extractions: list[LLMExtraction] = Field(default_factory=list, max_length=5)
    conversation_summary: str = ""
    extraction_notes: str = ""


class ConflictJudgment(BaseModel):
    is_contradiction: bool
    contradiction_type: Literal["DIRECT", "CONDITIONAL", "NONE"]
    explanation: str
    recommended_action: Literal["ACCEPT_NEW", "KEEP_OLD", "QUARANTINE_BOTH", "ESCALATE"]
    reasoning: str


class KnowledgeExtractor(Protocol):
    async def extract(self, transcript: str, worker: Worker) -> list[dict]:
        ...


class ConflictJudge(Protocol):
    async def judge(self, fact_a: dict, fact_b: dict) -> ConflictJudgment:
        ...


def openai_enabled() -> bool:
    return settings.llm_mode.lower() == "openai" and bool(settings.openai_api_key)


class OpenAIExtractor:
    async def extract(self, transcript: str, worker: Worker) -> list[dict]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.responses.parse(
            model=settings.openai_extraction_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You extract operational factory knowledge from worker transcripts. "
                        "Return only concrete, verifiable facts that can be checked later. "
                        "Ignore greetings, jokes, vague complaints, and pure speculation. "
                        "Prefer precision over recall. Use canonical snake_case entity and attribute names."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Worker: {worker.name}\n"
                        f"Department: {worker.department}\n"
                        f"Seniority: {worker.seniority_years} years\n\n"
                        f"Transcript:\n{transcript}"
                    ),
                },
            ],
            text_format=ExtractionResponse,
        )
        parsed: ExtractionResponse = response.output_parsed
        return [
            {
                "raw_text": item.raw_text,
                "structured_fact": item.structured_fact.model_dump(),
                "source_type": item.source_type,
                "is_likely_noise": item.is_likely_noise,
                "noise_reason": item.noise_reason,
                "llm_confidence": item.llm_confidence,
                "requires_verification": item.requires_verification,
            }
            for item in parsed.extractions
        ]


class OpenAIConflictJudge:
    async def judge(self, fact_a: dict, fact_b: dict) -> ConflictJudgment:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.responses.parse(
            model=settings.openai_judge_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You judge whether two factory operational facts contradict. "
                        "Different conditions usually mean compatibility, not contradiction. "
                        "Same entity, same attribute, same condition, different operational values usually conflict."
                    ),
                },
                {
                    "role": "user",
                    "content": f"FACT A:\n{fact_a}\n\nFACT B:\n{fact_b}",
                },
            ],
            text_format=ConflictJudgment,
        )
        return response.output_parsed


class DeterministicConflictJudge:
    async def judge(self, fact_a: dict, fact_b: dict) -> ConflictJudgment:
        from app.services.text import normalize_value, numeric_value

        same_condition = not fact_a.get("condition") or not fact_b.get("condition") or fact_a.get("condition") == fact_b.get("condition")
        left_num = numeric_value(str(fact_a.get("value", "")))
        right_num = numeric_value(str(fact_b.get("value", "")))
        if left_num is not None and right_num is not None:
            differs = abs(left_num - right_num) > 0.01
        else:
            differs = normalize_value(str(fact_a.get("value", ""))) != normalize_value(str(fact_b.get("value", "")))
        is_contradiction = bool(same_condition and differs)
        return ConflictJudgment(
            is_contradiction=is_contradiction,
            contradiction_type="DIRECT" if is_contradiction else ("CONDITIONAL" if not same_condition else "NONE"),
            explanation="Deterministic fallback based on entity, attribute, condition, and value equality.",
            recommended_action="QUARANTINE_BOTH" if is_contradiction else "ACCEPT_NEW",
            reasoning="Used offline judge because OpenAI LLM mode is disabled or unavailable.",
        )


def get_conflict_judge() -> ConflictJudge:
    return OpenAIConflictJudge() if openai_enabled() else DeterministicConflictJudge()

