# Minder AI — Knowledge Integration System
## Implementation Plan (Python + FastAPI)

> **Mục tiêu:** Xây dựng hệ thống tự học hỏi từ hội thoại nhà máy — thu thập, xác minh, tích hợp "tribal wisdom" và đưa nó vào agent phục vụ công nhân.

---

## Tổng quan Kiến trúc

```
[Worker Conversation]
        │  (transcript text)
        ▼
┌─────────────────────────────┐
│   Ingestion API (FastAPI)   │  ← Phase 1
└──────────────┬──────────────┘
               │
        ┌──────▼──────┐
        │ Extraction  │  ← Phase 2: LLM parses facts, entities
        │  Pipeline   │
        └──────┬──────┘
               │ KnowledgeItem (PENDING)
        ┌──────▼──────────────┐
        │ Verification &      │  ← Phase 3: noise filter, conflict
        │ Conflict Resolution │    resolution, state machine
        └──────┬──────────────┘
               │ (VERIFIED | QUARANTINED | ESCALATED)
        ┌──────▼──────┐
        │  Knowledge  │  ← Qdrant (vectors) + MySQL (structured)
        │    Store    │
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │  RAG Agent  │  ← Phase 4: serves knowledge back
        │  + Metrics  │    with measurable feedback loop
        └─────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11 + FastAPI + Uvicorn |
| LLM | OpenAI GPT-4o (extraction/judge) + GPT-4o-mini (retrieval/chat) |
| Vector Store | Qdrant (semantic search, knowledge retrieval) |
| Relational DB | MySQL 8.0 (structured facts, relations, metrics) |
| Graph Logic | MySQL self-referential relations table (no Neo4j needed) |
| Task Queue | FastAPI BackgroundTasks (demo async processing; production pilot would need a durable queue) |
| Demo UI | Vanilla HTML + CSS + JS (single-page dashboard) |
| Embedding | OpenAI `text-embedding-3-small` |
| ORM | SQLAlchemy 2.0 (async) |
| Migration | Alembic |
| Config | Pydantic Settings + `.env` |

> **Lý do không dùng Neo4j:** Quy mô nhà máy 50 người × 200 conv/ngày không cần distributed graph DB. MySQL với bảng `knowledge_relations` và recursive CTE queries là đủ, giảm complexity đáng kể.

---

## Cấu trúc Thư mục

```
minder_ai/
├── alembic/                    # DB migrations
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── conversation.py    # POST /conversations/ingest
│   │   │   ├── workers.py         # GET /workers for demo UI
│   │   │   ├── knowledge.py       # GET/PATCH knowledge items
│   │   │   ├── agent.py           # POST /agent/query (RAG endpoint)
│   │   │   └── metrics.py         # GET /metrics/dashboard
│   │   └── deps.py               # Dependency injection
│   ├── core/
│   │   ├── config.py             # Settings (env vars)
│   │   ├── database.py           # MySQL async engine
│   │   └── qdrant.py             # Qdrant client setup
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── knowledge_item.py
│   │   ├── knowledge_relation.py
│   │   ├── conversation.py
│   │   ├── worker.py
│   │   └── metric_snapshot.py
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── services/
│   │   ├── extraction/
│   │   │   ├── extractor.py      # LLM extraction pipeline
│   │   │   └── noise_filter.py   # Noise/joke/complaint detection
│   │   ├── verification/
│   │   │   ├── similarity.py     # Qdrant vector search
│   │   │   ├── conflict.py       # Contradiction detection
│   │   │   └── resolver.py       # Resolution strategy & state machine
│   │   ├── agent/
│   │   │   ├── rag.py            # Retrieval-Augmented Generation
│   │   │   └── context_builder.py
│   │   └── metrics/
│   │       ├── tracker.py        # Log utilization events
│   │       └── calculator.py     # Compute dashboard metrics
│   └── main.py                   # FastAPI app entry point
├── frontend/
│   ├── index.html                # Demo UI (single page)
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_extraction.py
│   ├── test_conflict.py
│   └── test_rag.py
├── scripts/
│   ├── seed_workers.py           # Seed demo data
│   ├── seed_sop_documents.py     # Seed 5-10 SOP chunks for demo conflict/RAG
│   └── simulate_conversations.py # Demo scenario runner
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## Phase Overview

| Phase | Tên | Deliverable chính |
|---|---|---|
| **1** | Core Infrastructure | DB schema, Qdrant setup, FastAPI skeleton |
| **2** | Knowledge Acquisition | Extraction pipeline, noise filter, PENDING items |
| **3** | Consistency & Conflict Resolution | Verification logic, state machine, conflict resolution |
| **4** | Feedback Loop & Metrics | RAG agent, metrics dashboard, demo UI |

---

## Các Quyết định Thiết kế Quan trọng (để Defend)

| Quyết định | Lý do |
|---|---|
| Không dùng Neo4j | MySQL self-referential table đủ cho 50 workers, giảm ops complexity |
| GPT-4o cho extraction/judge, GPT-4o-mini cho chat | Đủ mạnh cho structured output và demo RAG; pricing cần ghi là giá hiện hành có thể thay đổi |
| Async extraction (BackgroundTasks) | Chấp nhận cho demo kỹ thuật; production pilot cần queue bền vững |
| 2 Qdrant collections (SOP + tribal) | SOP seeded stub là nguồn chính thức cho demo; tribal chỉ augment |
| SOP wins policy | Nếu tribal knowledge khác SOP thì escalate, agent trả lời theo SOP và cảnh báo claim tribal cần review |
| 4 measurable metrics (CR, KBC, KAR, KUR) | KBC đo query có dùng tribal; KUR đo verified items thật sự được retrieve |

---

## Decisions Log

- ✅ LLM: OpenAI (GPT-4o extraction + GPT-4o-mini chat)
- ✅ Vector DB: Qdrant
- ✅ Relational DB: MySQL
- ✅ Graph: MySQL-native (self-referential `knowledge_relations` table)
- ✅ Scope: Code chạy được + tài liệu thiết kế
- ✅ UI: Demo dashboard (4 panels)
- ✅ Async: FastAPI BackgroundTasks (không cần Celery/Redis)
- ✅ Escalation: Dashboard only (không cần email/Slack)
- ✅ SOP: seeded stub trong Qdrant `sop_documents`, không build ingestion SOP đầy đủ
- ✅ Authority: SOP là nguồn chính thức; verified tribal không được override SOP

---

## Verification Plan

### Automated Tests
- `pytest` cho extraction, conflict logic, RAG pipeline
- Integration test: full conversation → knowledge item flow
- Unit test: 4 metrics tính đúng
- Unit test riêng KBC vs KUR để tránh nhầm `queries_with_tribal_knowledge` với `distinct_retrieved_items_7d`

### Manual Demo
- Chạy `scripts/simulate_conversations.py` để replay các scenario từ brief
- Mở dashboard UI, quan sát knowledge items chuyển state
- Gửi query qua `/agent/query` trước và sau khi có tribal wisdom

### Files Plan Chi tiết
- `01_Phase1_Infrastructure.md` — DB schema, Qdrant, FastAPI skeleton
- `02_Phase2_Knowledge_Acquisition.md` — Extraction pipeline, noise filter
- `03_Phase3_Conflict_Resolution.md` — State machine, conflict resolution
- `04_Phase4_Feedback_Metrics.md` — RAG agent, metrics, demo UI
