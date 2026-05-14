# Phase 2: Knowledge Acquisition Pipeline

> **Mục tiêu:** Biến transcript hội thoại thô → structured `KnowledgeItem` ở trạng thái `PENDING`. Đây là "đầu phễu" của hệ thống. Mục tiêu: **precision cao hơn recall** — thà bỏ sót một fact còn hơn nhập rác.

---

## Step 2.1 — API Endpoint: Ingest Conversation

### `POST /api/v1/conversations/ingest`

```python
class ConversationIngestRequest(BaseModel):
    worker_id: str
    transcript: str
    conversation_id: str | None = None

class ConversationIngestResponse(BaseModel):
    conversation_id: str
    status: str    # "processing"
    message: str   # "Transcript queued for extraction"
```

**Luồng xử lý:**
1. Validate `worker_id` tồn tại
2. Tạo `Conversation` record với `status=PENDING`
3. Trả về 202 Accepted ngay — **không block**
4. Kick off `BackgroundTask`: `run_extraction_pipeline(conversation_id)`

```python
@router.post("/ingest", status_code=202)
async def ingest_conversation(
    request: ConversationIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    conversation = await create_conversation(db, request)
    background_tasks.add_task(run_extraction_pipeline, conversation.id)
    return ConversationIngestResponse(
        conversation_id=conversation.id,
        status="processing",
        message="Transcript queued for extraction"
    )
```

> **Tại sao async?** Extraction call tốn 2-5 giây (LLM). Worker không cần chờ — agent trả lời xong, hệ thống học ngầm phía sau.

---

## Step 2.2 — LLM Extraction: Prompt Design

### Triết lý
Dùng **một LLM call duy nhất** (GPT-4o) với `response_format=json_schema`. Prompt thiết kế để:
1. Trích xuất facts **có thể kiểm chứng được** (không trừu tượng)
2. Phân loại: CORRECTION / TEACHING / WARNING
3. Tự đánh dấu noise/joke
4. Gắn metadata: entity, domain, condition

### System Prompt
```
You are a knowledge extraction specialist for a factory AI system.
Your job: analyze worker conversations and extract ONLY verifiable operational facts.

EXTRACTION RULES:
- Extract only concrete, actionable facts about factory operations
- Include: temperatures, settings, machine behaviors, timing, materials, exceptions, workarounds
- Ignore: greetings, complaints without specifics, clearly humorous statements, general chit-chat
- For each fact, assess if this is a CORRECTION of the AI, a TEACHING moment, or a WARNING

OUTPUT: Strict JSON. Extract 0-5 facts per conversation.
If no extractable operational facts, return empty array.
```

### User Prompt (template)
```
Worker: {worker_name} | Department: {department} | Seniority: {seniority_years} years

CONVERSATION TRANSCRIPT:
{transcript}

Extract operational knowledge facts from this conversation.
```

### JSON Schema (response_format)
```json
{
  "type": "object",
  "properties": {
    "extractions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "raw_text":     {"type": "string"},
          "structured_fact": {
            "type": "object",
            "properties": {
              "entity":    {"type": "string"},   // "station_3", "dryer_B"
              "attribute": {"type": "string"},   // "welding_current", "temperature"
              "value":     {"type": "string"},   // "5% lower", "75°C"
              "unit":      {"type": "string"},   // "celsius", "ampere"
              "condition": {"type": "string"},   // "after_lunch_tuesday"
              "domain":    {"type": "string"}    // "welding", "laundry", "safety"
            },
            "required": ["entity", "attribute", "value", "domain"]
          },
          "source_type":          {"type": "string", "enum": ["WORKER_CORRECTION","WORKER_TEACHING","WORKER_WARNING","AMBIGUOUS"]},
          "is_likely_noise":      {"type": "boolean"},
          "noise_reason":         {"type": "string"},
          "llm_confidence":       {"type": "number"},
          "requires_verification":{"type": "boolean"}
        },
        "required": ["raw_text", "structured_fact", "source_type", "llm_confidence"]
      }
    },
    "conversation_summary": {"type": "string"},
    "extraction_notes":     {"type": "string"}
  }
}
```

---

## Step 2.3 — Noise Filter

LLM đánh dấu `is_likely_noise` nhưng cần **rule-based scoring bổ sung** để tránh over-reliance.

### Noise Score Computation

```python
def compute_noise_score(extraction: dict, worker: Worker) -> float:
    score = 0.0

    if extraction.get("is_likely_noise"):         score += 0.50
    if extraction.get("llm_confidence", 0.5) < 0.4: score += 0.30
    elif extraction.get("llm_confidence") < 0.6:   score += 0.10
    if extraction.get("source_type") == "AMBIGUOUS": score += 0.20

    # Value quá mơ hồ (không có số)
    value = extraction["structured_fact"].get("value", "")
    if not any(c.isdigit() for c in value) and len(value.split()) > 5:
        score += 0.15

    # Junior worker nói về safety → tăng skepticism
    if worker.seniority_years < 1 and extraction["structured_fact"].get("domain") == "safety":
        score += 0.20

    return min(score, 1.0)
```

### Acceptance Thresholds

| noise_score | Quyết định |
|---|---|
| 0.00 – 0.35 | ✅ Tạo KnowledgeItem → Phase 3 xử lý |
| 0.35 – 0.65 | ⚠️ Tạo KnowledgeItem với `status=QUARANTINED`; không chạy auto-verification cho đến khi có evidence mới |
| 0.65 – 1.00 | ❌ Discard — ghi audit/log extraction nhưng không tạo item active |

---

## Step 2.4 — Confidence Score Computation

```python
def compute_confidence_score(extraction: dict, worker: Worker) -> float:
    score = extraction.get("llm_confidence", 0.5)

    # Seniority bonus (max 20 years → +0.2)
    score += min(worker.seniority_years / 20, 1.0) * 0.2

    # Trust score từ lịch sử (accumulated)
    score = score * 0.7 + worker.trust_score * 0.3

    # Source type bonus
    source_bonuses = {
        "WORKER_CORRECTION": +0.10,
        "WORKER_TEACHING":   +0.05,
        "WORKER_WARNING":    +0.05,
        "AMBIGUOUS":         -0.10,
    }
    score += source_bonuses.get(extraction.get("source_type", "AMBIGUOUS"), 0)

    return max(0.0, min(score, 1.0))
```

---

## Step 2.5 — Embedding & Qdrant Indexing

```python
async def embed_and_index_knowledge_item(item: KnowledgeItem, openai_client):
    # Build rich embed text (fact + context)
    embed_text = (
        f"Entity: {item.structured_fact['entity']}. "
        f"Attribute: {item.structured_fact['attribute']}. "
        f"Value: {item.structured_fact['value']}. "
        f"Condition: {item.structured_fact.get('condition', 'general')}. "
        f"Domain: {item.structured_fact['domain']}. "
        f"Original: {item.raw_text}"
    )

    response = await openai_client.embeddings.create(
        model="text-embedding-3-small", input=embed_text
    )
    vector = response.data[0].embedding

    qdrant_id = str(uuid4())
    await qdrant_client.upsert(
        collection_name="tribal_knowledge",
        points=[PointStruct(
            id=qdrant_id,
            vector=vector,
            payload={
                "knowledge_item_id": str(item.id),
                "status":      item.status,
                "domain":      item.structured_fact.get("domain"),
                "entity":      item.structured_fact.get("entity"),
                "attribute":   item.structured_fact.get("attribute"),
                "source_type": item.source_type,
            }
        )]
    )
    return qdrant_id
```

---

## Step 2.6 — Full Extraction Pipeline

```
run_extraction_pipeline(conversation_id):
  1. Load conversation + worker từ DB
  2. Gọi LLM extractor → list[extraction]
  3. For each extraction:
     a. compute noise_score
     b. if noise_score > 0.65 → skip (log only)
     c. compute confidence_score
     d. Tạo KnowledgeItem (PENDING hoặc QUARANTINED tùy noise)
     e. embed_and_index → Qdrant
     f. Save to MySQL
  4. Update conversation.status = DONE
  5. Trigger Phase 3 verification pipeline chỉ cho items còn `PENDING`
  6. Ghi skipped extraction vào `conversations.raw_extractions`; chỉ ghi `knowledge_audit_logs` cho item đã được tạo rồi chuyển QUARANTINED/REJECTED
```

---

## Step 2.7 — Status Polling API

```
GET /api/v1/conversations/{conversation_id}/status
→ {status, extracted_count, quarantined_count, skipped_count}
```

---

## Cost Analysis

| Operation | Model | Est. Tokens | Cost/conv |
|---|---|---|---|
| Extraction | GPT-4o | ~800 in + ~400 out | theo pricing OpenAI hiện hành |
| Embedding (3 facts) | text-embedding-3-small | ~300 | theo pricing OpenAI hiện hành |
| **Total** | | | Dự kiến dưới mức "pennies per conversation"; cần benchmark thực tế vì pricing/model có thể thay đổi |

Budget "pennies per conversation" = **mục tiêu demo**, không hard guarantee. Ghi lại token usage theo conversation để chứng minh sau khi chạy.

---

## Checklist Phase 2

- [ ] `POST /conversations/ingest` nhận transcript, trả 202 ngay
- [ ] BackgroundTask extraction không block API response
- [ ] LLM trả JSON đúng schema với `response_format`
- [ ] Noise filter loại bỏ joke/complaint (noise_score > 0.65)
- [ ] KnowledgeItem được tạo đúng status (PENDING/QUARANTINED)
- [ ] QUARANTINED do noise trung bình không bị Phase 3 auto-verify ngay
- [ ] Vector embedding được index lên Qdrant
- [ ] Skipped extraction được lưu trong `raw_extractions`; QUARANTINED/REJECTED item có audit log
- [ ] Polling `GET /conversations/{id}/status` hoạt động
- [ ] Test: transcript có fact rõ + joke + complaint + correction → đúng kết quả
