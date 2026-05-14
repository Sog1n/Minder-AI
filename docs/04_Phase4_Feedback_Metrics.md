# Phase 4: Feedback Loop, Metrics & Demo UI

> **Mục tiêu:** Đóng vòng lặp — integrated knowledge được phục vụ lại cho agent, mọi phản hồi của worker được track, và dashboard chứng minh hệ thống đang học. "The agent got better" phải là một số, không phải cảm giác.

---

## Step 4.1 — RAG Agent: Query Endpoint

### `POST /api/v1/agent/query`

```python
class AgentQueryRequest(BaseModel):
    worker_id: str
    query: str
    conversation_id: str | None = None

class AgentQueryResponse(BaseModel):
    response: str
    sources: list[KnowledgeSource]   # items được dùng
    retrieval_latency_ms: int
    generation_latency_ms: int
    latency_ms: int
    used_tribal_knowledge: bool       # flag cho metrics
    query_log_id: str                 # để track correction
```

---

## Step 4.2 — Hybrid Retrieval Strategy

### Triết lý: "SOP Official, Tribal Augments"

```
Worker Query
     │
     ├──► [SOP Vector Search]         → top 3 SOP chunks
     │
     └──► [Tribal Knowledge Search]   → top 5 VERIFIED items only
               │                        (filter: status = VERIFIED)
               ▼
         [Context Ranker & Merger]
               │
               ▼
         [LLM Generation] (gpt-4o-mini, streaming preferred)
```

### Context Builder (`services/agent/context_builder.py`)

```python
async def build_context(query, worker_id, query_log_id, qdrant_client, db):
    query_vector = await get_embedding(query)

    # 1. Tribal knowledge (VERIFIED only)
    tribal_results = await qdrant_client.search(
        collection_name="tribal_knowledge",
        query_vector=query_vector,
        limit=5,
        query_filter=Filter(must=[
            FieldCondition(key="status", match=MatchValue(value="VERIFIED"))
        ]),
        with_payload=True,
    )

    # 2. SOP search
    sop_results = await qdrant_client.search(
        collection_name="sop_documents",
        query_vector=query_vector,
        limit=3,
        with_payload=True,
    )

    # 3. Rank & merge
    ranked_context = rank_context_items(tribal_results, sop_results, query)
    used_knowledge_ids = [r.payload["knowledge_item_id"]
                          for r in tribal_results if r.score > 0.75]
    await log_retrieval_events(db, query_log_id, [
        r for r in tribal_results if r.payload["knowledge_item_id"] in used_knowledge_ids
    ])

    return AgentContext(
        items=ranked_context,
        used_knowledge_ids=used_knowledge_ids,
        used_sop_chunks=[r.payload.get("chunk_id") for r in sop_results],
    )
```

### System Prompt cho RAG

```
You are Minder, a voice-first AI co-worker for factory workers.

KNOWLEDGE HIERARCHY (strict priority):
1. SOP DOCUMENTS — official procedures and default answer
2. VERIFIED TRIBAL KNOWLEDGE — practical augmentations from experienced workers
3. General knowledge — fallback only

RULES:
- If verified tribal knowledge contradicts SOP, answer according to SOP and mention that a field claim requires supervisor review
- If unsure: "I'm not certain — please verify with a supervisor"
- Keep answers short and actionable (workers are on the floor)
- Never hallucinate specific numbers (temperatures, timing, settings)

SOP REFERENCE:
{sop_context}

VERIFIED TRIBAL KNOWLEDGE (augmentations only):
{tribal_context}
```

---

## Step 4.3 — Correction Tracking

Correction = tín hiệu học hỏi quan trọng nhất.

```
PATCH /api/v1/agent/{query_log_id}/correct
Body: {
  "correction_text": "Actually drop current by 5%, not 3%",
  "worker_id": "..."
}
```

**Backend actions:**
1. Set `agent_query_logs.was_corrected = TRUE`
2. Auto-tạo `Conversation` mới với transcript = correction_text + source_type = `WORKER_CORRECTION`
3. Trigger extraction pipeline → new KnowledgeItem (với confidence bonus vì là CORRECTION)
4. Giảm `trust_score` của knowledge item đã được serve (nếu liên quan)
5. Ghi `knowledge_audit_logs` cho trust adjustment và correction source

---

## Step 4.4 — The 4 Measurable Metrics

### Metric 1: Correction Rate (CR)
> Tỷ lệ queries agent bị sửa. Phải **GIẢM** theo thời gian.

```
CR = corrections_count / total_queries
```
**Target:** CR < 15% sau 30 ngày.

---

### Metric 2: KB Coverage Score (KBC)
> % queries được trả lời có dùng ít nhất một verified tribal knowledge item. Phải **TĂNG** theo thời gian.

```
KBC = queries_with_tribal_knowledge / total_queries
```
**Target:** KBC > 40% sau 2 tuần.

---

### Metric 3: Knowledge Acceptance Rate (KAR)
> % items PENDING → VERIFIED (không bị reject). Đo extraction precision.

```
KAR = verified_count / (verified_count + rejected_count)
```
**Target:** KAR > 60%.

---

### Metric 4: Knowledge Utilization Rate (KUR)
> % VERIFIED items được retrieve ít nhất 1 lần/tuần. Đo "sống" của KB, khác với KBC vì mẫu số là knowledge items chứ không phải queries.

```
KUR = distinct_retrieved_items_7d / total_verified_items
```
**Target:** KUR > 50% (tránh dead knowledge).

---

## Step 4.5 — Daily Metric Snapshot Job

```python
async def take_daily_snapshot(db: AsyncSession):
    today = date.today()

    total     = await count_knowledge_items(db)
    verified  = await count_by_status(db, "VERIFIED")
    quarantined = await count_by_status(db, "QUARANTINED")
    escalated = await count_by_status(db, "ESCALATED")
    rejected = await count_by_status(db, "REJECTED")
    superseded = await count_by_status(db, "SUPERSEDED")

    yesterday = today - timedelta(days=1)
    logs = await get_logs_for_date(db, yesterday)
    total_queries = len(logs)
    corrections   = sum(1 for l in logs if l.was_corrected)
    queries_with_tribal = sum(1 for l in logs if l.used_knowledge_ids)
    verified_items = await count_by_status(db, "VERIFIED")
    distinct_retrieved_items_7d = await count_distinct_retrieved_verified_items(
        db,
        since=today - timedelta(days=7),
    )

    snapshot = MetricSnapshot(
        snapshot_date=today,
        total_knowledge_items=total,
        verified_count=verified,
        quarantined_count=quarantined,
        escalated_count=escalated,
        rejected_count=rejected,
        superseded_count=superseded,
        total_queries=total_queries,
        correction_rate=corrections / total_queries if total_queries else 0,
        kb_coverage_score=queries_with_tribal / total_queries if total_queries else 0,
        knowledge_utilization_rate=(
            distinct_retrieved_items_7d / verified_items if verified_items else 0
        ),
        knowledge_acceptance_rate=await compute_kar(db),
        avg_confidence_score=await avg_confidence(db, "VERIFIED"),
    )
    db.add(snapshot)
    await db.commit()
```

### Metrics API

```
GET /api/v1/metrics/dashboard
→ {
    today:        {correction_rate, kbc_score, kar, kur, verified_count, ...},
    trend_7d:     [{date, correction_rate, kbc_score}, ...],
    top_domains:  [{domain, count, avg_confidence}],
    pending_review: {quarantined_count, escalated_count}
  }
```

---

## Step 4.6 — Demo UI Layout (4 Panels)

```
┌─────────────────────────────────────────────────────────┐
│  🏭 Minder AI — Knowledge System Dashboard              │
├──────────────────────┬──────────────────────────────────┤
│  Panel 1             │  Panel 2                         │
│  [Conversation       │  [Knowledge Browser]             │
│   Simulator]         │  Filter: Status | Domain         │
│                      │  List: facts + status badges     │
│  POST transcript →   │  PATCH: verify/reject            │
│  watch extraction    │                                  │
├──────────────────────┼──────────────────────────────────┤
│  Panel 3             │  Panel 4                         │
│  [Conflict Viewer]   │  [Learning Metrics]              │
│                      │                                  │
│  List conflict pairs │  📈 Correction Rate (line chart) │
│  + LLM explanation   │  📊 KB Coverage Score            │
│  Accept A | Accept B │  ✅ Knowledge Acceptance Rate    │
│  Quarantine Both     │  📦 Items by status (donut)      │
└──────────────────────┴──────────────────────────────────┘
```

### Panel 1: Conversation Simulator
- Textarea nhập transcript
- Dropdown chọn worker (fetch `/api/v1/workers`)
- Button "Submit" → `POST /conversations/ingest`
- Poll `/conversations/{id}/status` mỗi 2 giây
- Hiển thị extracted facts realtime

### Panel 2: Knowledge Browser
- Fetch `GET /api/v1/knowledge?status=PENDING&limit=20`
- Status badges: PENDING=yellow, VERIFIED=green, QUARANTINED=orange, ESCALATED=red
- Click item → xem `structured_fact` JSON
- Button "Verify" / "Reject" → `PATCH /knowledge/{id}/resolve`

### Panel 3: Conflict Viewer
- Fetch `GET /api/v1/knowledge/conflicts`
- Side-by-side: item_a vs item_b + LLM explanation + recommended action
- Supervisor chọn: Accept A | Accept B | Quarantine Both

### Panel 4: Learning Metrics (Chart.js)
- Line chart: correction_rate trend 7 ngày
- Donut chart: items by status
- Number cards: KBC, KAR, KUR với target indicators
- Auto-refresh mỗi 30 giây

---

## Step 4.7 — Demo Simulation Script

```python
# scripts/simulate_conversations.py
# 5 scenarios từ brief để demo end-to-end

SCENARIOS = [
    {
        "name": "Scenario 1: New tribal wisdom (no conflict)",
        "worker": "Maria - 10 years, laundry dept",
        "transcript": (
            "The AI keeps telling me to use the standard cycle for Hotel A polyester. "
            "That's completely wrong. Hotel A polyester always shrinks when mixed with cotton. "
            "You MUST separate them or you'll ruin the batch."
        ),
        "expected": "VERIFIED (high confidence, no conflict)",
    },
    {
        "name": "Scenario 2: Correction with specific numbers",
        "worker": "Carlos - 8 years, welding dept",
        "transcript": (
            "Station 3 always overheats after lunch on Tuesdays. "
            "I drop the current by 5% every time. The AI told me 3% but that is not enough. "
            "Trust me, 5% is the right number."
        ),
        "expected": "VERIFIED (WORKER_CORRECTION source type, high confidence)",
    },
    {
        "name": "Scenario 3a: Conflict setup - Worker A",
        "worker": "Worker A - 5 years",
        "transcript": "The dryer at station 2 should run at 80 degrees Celsius.",
        "expected": "PENDING → conflict with Scenario 3b → QUARANTINED",
    },
    {
        "name": "Scenario 3b: Conflict setup - Worker B",
        "worker": "Worker B - 3 years",
        "transcript": "No, the dryer at station 2 runs at 75 degrees. I checked this morning.",
        "expected": "QUARANTINED (contradicts 3a, similar trust weight)",
    },
    {
        "name": "Scenario 4: Noise - should be discarded",
        "worker": "New Hire - 0 years",
        "transcript": (
            "Haha I bet this machine runs on hopes and dreams. "
            "Also I'm not sure but maybe 90 degrees? Just guessing lol."
        ),
        "expected": "DISCARDED (noise_score > 0.65)",
    },
]
```

---

## Latency Budget Verification

| Operation | Budget | Implementation | Status |
|---|---|---|---|
| Retrieval only | p95 < 300ms | Qdrant SOP + tribal search + MySQL hydration | Target |
| Agent first token / stream start | < 1000ms | Stream GPT-4o-mini response after context build | Target |
| Full LLM response | Measure separately | Depends on answer length and model latency; do not hard-guarantee < 1s | Benchmark |
| Extraction (background) | No budget (async) | GPT-4o ~2s (không block worker) | ✅ |
| Metrics dashboard | < 500ms | Cached daily snapshot | ✅ |

---

## Checklist Phase 4

- [ ] Retrieval p95 < 300ms (benchmark với httpx)
- [ ] First token/stream start < 1 giây; full response đo riêng
- [ ] Chỉ VERIFIED items xuất hiện trong RAG context
- [ ] Nếu VERIFIED tribal khác SOP, agent trả lời theo SOP và nêu claim tribal cần review
- [ ] `PATCH /agent/{id}/correct` tự động tạo conversation mới + trigger extraction
- [ ] Correction giảm trust phải ghi `knowledge_audit_logs`
- [ ] 4 metrics (CR, KBC, KAR, KUR) tính đúng; KBC và KUR có unit test riêng
- [ ] Daily snapshot job chạy khi startup
- [ ] `GET /metrics/dashboard` trả đúng format
- [ ] Demo UI: 4 panels load, tất cả buttons hoạt động
- [ ] `simulate_conversations.py` chạy 5 scenarios thành công
- [ ] Verify: Scenario 3 → cả 2 items QUARANTINED
- [ ] Verify: Scenario 1 (Maria) → item VERIFIED, xuất hiện trong context khi query về polyester
