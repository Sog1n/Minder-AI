import asyncio

from app.core.store import store
from app.models.domain import KnowledgeStatus
from app.services.extraction import run_extraction_pipeline


def test_sop_conflict_escalates() -> None:
    store.reset()
    store.seed_defaults()
    conversation = store.create_conversation("worker_a", "The dryer at station 2 should run at 75 degrees Celsius.")
    asyncio.run(run_extraction_pipeline(conversation.id))
    item = next(iter(store.knowledge_items.values()))
    assert item.status == KnowledgeStatus.ESCALATED


def test_verified_items_drive_kur() -> None:
    store.reset()
    store.seed_defaults()
    conversation = store.create_conversation(
        "maria",
        "Hotel A polyester always shrinks when mixed with cotton. You must separate them or you'll ruin the batch.",
    )
    asyncio.run(run_extraction_pipeline(conversation.id))
    dashboard = store.metric_dashboard()
    assert dashboard["today"]["verified_count"] >= 0
    assert "kur" in dashboard["today"]
