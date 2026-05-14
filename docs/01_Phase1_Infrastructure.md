# Phase 1: Core Infrastructure & Data Model

> **Mục tiêu:** Dựng toàn bộ nền móng — DB schema, Qdrant collections, FastAPI app skeleton, environment config.

---

## Step 1.1 — Environment & Dependencies

### `requirements.txt`
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.36
aiomysql==0.2.0
alembic==1.13.3
qdrant-client==1.12.0
openai==1.54.0
pydantic==2.9.2
pydantic-settings==2.6.0
python-dotenv==1.0.1
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
```

### `.env.example`
```env
OPENAI_API_KEY=sk-...
OPENAI_EXTRACTION_MODEL=gpt-4o
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=secret
MYSQL_DATABASE=minder_ai

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_KNOWLEDGE=tribal_knowledge
QDRANT_COLLECTION_SOP=sop_documents

APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
```

### `docker-compose.yml`
```yaml
version: "3.9"
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: secret
      MYSQL_DATABASE: minder_ai
    ports: ["3306:3306"]
    volumes: ["mysql_data:/var/lib/mysql"]
  qdrant:
    image: qdrant/qdrant:v1.12.0
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrant_data:/qdrant/storage"]
volumes:
  mysql_data:
  qdrant_data:
```

---

## Step 1.2 — MySQL Schema Design

### Triết lý thiết kế
- **`knowledge_items`**: bảng trung tâm — mỗi record là một "fact" với vòng đời state machine.
- **`knowledge_relations`**: bảng tự tham chiếu — "knowledge graph" nhúng trong MySQL (SUPPORTS, CONTRADICTS, SUPERSEDES, REFINES).
- **`workers`**: lưu `trust_score` — yếu tố trọng số trong conflict resolution.
- **`agent_query_logs`**: tracking RAG usage → phục vụ metrics.
- **`knowledge_support_evidence`**: lưu worker nào đã confirm item nào → promote bằng distinct workers.
- **`knowledge_retrieval_events`**: log từng verified item được retrieve → tính KUR đúng.
- **`knowledge_audit_logs`**: log mọi state transition/trust adjustment → rollback và anti-poisoning.
- **`metric_snapshots`**: snapshot hàng ngày cho dashboard.

### DDL — Toàn bộ bảng

```sql
-- 1. Workers
CREATE TABLE workers (
    id              VARCHAR(36)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    department      VARCHAR(100),
    seniority_years INT          DEFAULT 0,
    trust_score     FLOAT        DEFAULT 0.5,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- 2. Conversations
CREATE TABLE conversations (
    id                VARCHAR(36)  PRIMARY KEY,
    worker_id         VARCHAR(36)  NOT NULL,
    transcript        TEXT         NOT NULL,
    processed_at      DATETIME,
    extraction_status ENUM('PENDING','PROCESSING','DONE','FAILED') DEFAULT 'PENDING',
    raw_extractions   JSON,
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id)
);

-- 3. Knowledge Items (core table)
CREATE TABLE knowledge_items (
    id                  VARCHAR(36)  PRIMARY KEY,
    raw_text            TEXT         NOT NULL,
    structured_fact     JSON         NOT NULL,   -- {entity, attribute, value, unit, condition, domain}
    conversation_id     VARCHAR(36),
    worker_id           VARCHAR(36),
    source_type         ENUM('WORKER_CORRECTION','WORKER_TEACHING','WORKER_WARNING','AMBIGUOUS') NOT NULL,
    status              ENUM('PENDING','VERIFIED','QUARANTINED','ESCALATED','REJECTED','SUPERSEDED') DEFAULT 'PENDING',
    confidence_score    FLOAT        DEFAULT 0.5,
    noise_score         FLOAT        DEFAULT 0.0,
    support_count       INT          DEFAULT 1,
    contradiction_count INT          DEFAULT 0,
    qdrant_vector_id    VARCHAR(36),
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    verified_at         DATETIME,
    resolution_note     TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (worker_id) REFERENCES workers(id),
    INDEX idx_status (status),
    INDEX idx_worker (worker_id),
    INDEX idx_created (created_at)
);

-- 4. Knowledge Relations (graph trong MySQL)
CREATE TABLE knowledge_relations (
    id              VARCHAR(36)  PRIMARY KEY,
    source_id       VARCHAR(36)  NOT NULL,
    target_id       VARCHAR(36)  NOT NULL,
    relation_type   ENUM('SUPPORTS','CONTRADICTS','SUPERSEDES','REFINES') NOT NULL,
    similarity_score FLOAT,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES knowledge_items(id),
    FOREIGN KEY (target_id) REFERENCES knowledge_items(id),
    UNIQUE KEY uq_relation (source_id, target_id, relation_type)
);

-- 5. Agent Query Logs
CREATE TABLE agent_query_logs (
    id                 VARCHAR(36)  PRIMARY KEY,
    worker_id          VARCHAR(36),
    query_text         TEXT         NOT NULL,
    response_text      TEXT,
    used_knowledge_ids JSON,
    used_sop_chunks    JSON,
    was_corrected      BOOLEAN      DEFAULT FALSE,
    correction_text    TEXT,
    retrieval_latency_ms INT,
    generation_latency_ms INT,
    latency_ms         INT,
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id)
);

-- 6. Knowledge Support Evidence
CREATE TABLE knowledge_support_evidence (
    id                 VARCHAR(36)  PRIMARY KEY,
    knowledge_item_id  VARCHAR(36)  NOT NULL,
    worker_id          VARCHAR(36)  NOT NULL,
    supporting_item_id VARCHAR(36),
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_item_id) REFERENCES knowledge_items(id),
    FOREIGN KEY (worker_id) REFERENCES workers(id),
    FOREIGN KEY (supporting_item_id) REFERENCES knowledge_items(id),
    UNIQUE KEY uq_support_worker (knowledge_item_id, worker_id)
);

-- 7. Knowledge Retrieval Events
CREATE TABLE knowledge_retrieval_events (
    id                 VARCHAR(36)  PRIMARY KEY,
    query_log_id       VARCHAR(36)  NOT NULL,
    knowledge_item_id  VARCHAR(36)  NOT NULL,
    similarity_score   FLOAT,
    rank_position      INT,
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (query_log_id) REFERENCES agent_query_logs(id),
    FOREIGN KEY (knowledge_item_id) REFERENCES knowledge_items(id),
    INDEX idx_retrieval_item_created (knowledge_item_id, created_at)
);

-- 8. Knowledge Audit Logs
CREATE TABLE knowledge_audit_logs (
    id                 VARCHAR(36)  PRIMARY KEY,
    knowledge_item_id  VARCHAR(36)  NOT NULL,
    actor_type         ENUM('SYSTEM','SUPERVISOR','WORKER') NOT NULL,
    actor_id           VARCHAR(36),
    action             VARCHAR(80)  NOT NULL,
    from_status        VARCHAR(32),
    to_status          VARCHAR(32),
    note               TEXT,
    metadata           JSON,
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_item_id) REFERENCES knowledge_items(id),
    INDEX idx_audit_item_created (knowledge_item_id, created_at)
);

-- 9. Metric Snapshots
CREATE TABLE metric_snapshots (
    id                         VARCHAR(36)  PRIMARY KEY,
    snapshot_date              DATE         NOT NULL UNIQUE,
    total_knowledge_items      INT          DEFAULT 0,
    verified_count             INT          DEFAULT 0,
    quarantined_count          INT          DEFAULT 0,
    escalated_count            INT          DEFAULT 0,
    rejected_count             INT          DEFAULT 0,
    superseded_count           INT          DEFAULT 0,
    pending_count              INT          DEFAULT 0,
    total_conversations        INT          DEFAULT 0,
    total_queries              INT          DEFAULT 0,
    correction_rate            FLOAT,
    kb_coverage_score          FLOAT,
    knowledge_utilization_rate FLOAT,
    avg_confidence_score       FLOAT,
    knowledge_acceptance_rate  FLOAT,
    created_at                 DATETIME     DEFAULT CURRENT_TIMESTAMP
);
```

---

## Step 1.3 — Qdrant Collections Setup

```
tribal_knowledge (collection)
├── vector_size: 1536  (text-embedding-3-small)
├── distance: Cosine
└── payload: knowledge_item_id, status, domain, entity, attribute, source_type

sop_documents (collection)  [seeded stub cho demo; SOP ingestion đầy đủ vẫn out of scope]
├── vector_size: 1536
└── payload: doc_id, chunk_id, page, section, source_file, domain, entity, attribute, value, unit, condition
```

> **Tại sao tách 2 collections?** Cho phép filter và weight khác nhau. Agent query cả hai với priority: SOP official > tribal_knowledge (VERIFIED) > fallback. Tribal knowledge không được override SOP; contradiction với SOP phải `ESCALATED`.

### Init script (`app/core/qdrant.py`)
```python
async def init_qdrant_collections(client: AsyncQdrantClient):
    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}
    if "tribal_knowledge" not in existing:
        await client.create_collection(
            collection_name="tribal_knowledge",
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
        await client.create_payload_index("tribal_knowledge", "status", PayloadSchemaType.KEYWORD)
        await client.create_payload_index("tribal_knowledge", "domain", PayloadSchemaType.KEYWORD)
        await client.create_payload_index("tribal_knowledge", "entity", PayloadSchemaType.KEYWORD)
    if "sop_documents" not in existing:
        await client.create_collection(
            collection_name="sop_documents",
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
        await client.create_payload_index("sop_documents", "domain", PayloadSchemaType.KEYWORD)
        await client.create_payload_index("sop_documents", "entity", PayloadSchemaType.KEYWORD)
        await client.create_payload_index("sop_documents", "attribute", PayloadSchemaType.KEYWORD)
```

---

## Step 1.4 — FastAPI Skeleton

### `app/core/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    openai_extraction_model: str = "gpt-4o"
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str
    mysql_database: str = "minder_ai"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_knowledge: str = "tribal_knowledge"

    class Config:
        env_file = ".env"

settings = Settings()
```

### `app/main.py`
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.v1 import conversation, knowledge, agent, metrics
from app.api.v1 import workers

app = FastAPI(title="Minder AI Knowledge System", version="1.0.0")

@app.on_event("startup")
async def startup():
    await init_db()
    await init_qdrant_collections(qdrant_client)

app.include_router(conversation.router, prefix="/api/v1/conversations", tags=["Conversations"])
app.include_router(workers.router,      prefix="/api/v1/workers",       tags=["Workers"])
app.include_router(knowledge.router,    prefix="/api/v1/knowledge",     tags=["Knowledge"])
app.include_router(agent.router,        prefix="/api/v1/agent",         tags=["Agent"])
app.include_router(metrics.router,      prefix="/api/v1/metrics",       tags=["Metrics"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

---

## Step 1.5 — Alembic Migration

```bash
alembic init alembic
# Chỉnh alembic/env.py trỏ đến SQLAlchemy models
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

---

## Checklist Phase 1

- [ ] `docker-compose up` → MySQL + Qdrant chạy OK
- [ ] `.env` đã config với credentials
- [ ] `alembic upgrade head` → 9 bảng được tạo
- [ ] `init_qdrant_collections()` → `tribal_knowledge` collection tồn tại với payload indexes
- [ ] `init_qdrant_collections()` → `sop_documents` collection tồn tại với payload indexes
- [ ] `uvicorn app.main:app --reload` → server khởi động, `/docs` accessible
- [ ] Seed 3 workers test bằng `scripts/seed_workers.py`
- [ ] Seed 5-10 SOP chunks demo bằng `scripts/seed_sop_documents.py`
- [ ] `GET /api/v1/workers` trả list workers cho dashboard
