# Phase 3: Consistency & Conflict Resolution

> **Mục tiêu:** Phần khó nhất và quan trọng nhất. Chỉ `PENDING` item đi qua auto-verification pipeline: tìm SOP conflict → tìm worker conflict/support → phán xét → phân giải → ra trạng thái `VERIFIED`, `QUARANTINED`, `ESCALATED`, `REJECTED`, hoặc làm item cũ thành `SUPERSEDED`.

---

## Step 3.1 — State Machine (Vòng đời Knowledge Item)

```
                ┌─────────┐
   Extraction   │ PENDING │
   ─────────────►         │
                └────┬────┘
                     │ verification pipeline
          ┌──────────┼──────────┬───────────┐
          ▼          ▼          ▼           ▼
     ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
     │VERIFIED │ │QUARANTINE│ │ESCALATED│ │ REJECTED │
     │(active) │ │(watching)│ │(human)  │ │discarded │
     └────┬────┘ └────┬─────┘ └────┬────┘ └──────────┘
          │           │            │
          │  new evidence          │ human decision
          ▼           ▼            ▼
     SUPERSEDED   (VERIFIED    (VERIFIED,
     old item      or REJECTED)  REJECTED, or
                               QUARANTINED)
```

### Transition Rules

| Từ | Đến | Điều kiện |
|---|---|---|
| PENDING | VERIFIED | confidence ≥ 0.7 AND no critical contradiction |
| PENDING | QUARANTINED | contradiction với VERIFIED item, chưa rõ ai đúng |
| PENDING | ESCALATED | contradicts SOP document, hoặc safety-critical |
| PENDING | REJECTED | noise_score > 0.65, hoặc human reject |
| VERIFIED | SUPERSEDED | item mới được supervisor hoặc trust-weighted rule chọn thay thế |
| QUARANTINED | VERIFIED | ≥2 workers khác nhau confirm + support_count tăng |
| QUARANTINED | REJECTED | contradiction resolved, item này sai |
| ESCALATED | VERIFIED/REJECTED | human supervisor quyết định qua dashboard |

---

## Step 3.2 — Semantic Similarity Search (Finding Conflicts)

### 2-Stage Search Strategy

**Stage 0 — Structured first** (MySQL): cùng `entity AND attribute`, status trong `VERIFIED`, `QUARANTINED`, `ESCALATED`.

**Stage 1 — Semantic fallback** (Qdrant): top-10 items cosine similarity > 0.70 để gợi ý review khi extractor đặt entity/attribute khác nhau.

**Stage 2 — Narrow** (MySQL): chỉ giữ item cùng `entity AND attribute`; trường hợp chỉ cùng entity hoặc chỉ cùng attribute đưa vào review suggestions, không auto-resolve.

```python
async def find_related_items(
    new_item: KnowledgeItem,
    qdrant_client,
    db: AsyncSession,
    top_k: int = 10,
    similarity_threshold: float = 0.70
) -> list[RelatedItem]:
    # Stage 0: exact structured match first
    exact_matches = await find_items_by_entity_attribute(
        db,
        entity=new_item.structured_fact.get("entity"),
        attribute=new_item.structured_fact.get("attribute"),
        statuses=["VERIFIED", "QUARANTINED", "ESCALATED"],
    )

    # Stage 1: Qdrant semantic fallback
    new_vector = await get_embedding(new_item.embed_text)
    results = await qdrant_client.search(
        collection_name="tribal_knowledge",
        query_vector=new_vector,
        limit=top_k,
        score_threshold=similarity_threshold,
        query_filter=Filter(
            must_not=[FieldCondition(
                key="knowledge_item_id",
                match=MatchValue(value=str(new_item.id))
            )]
        ),
        with_payload=True,
    )

    # Stage 2: MySQL narrow filter (same entity AND same attribute)
    related = []
    for db_item in exact_matches:
        related.append(RelatedItem(item=db_item, similarity=1.0, match_type="STRUCTURED"))

    for result in results:
        db_item = await get_knowledge_item(db, result.payload["knowledge_item_id"])
        if db_item and (
            db_item.structured_fact.get("entity") == new_item.structured_fact.get("entity")
            and db_item.structured_fact.get("attribute") == new_item.structured_fact.get("attribute")
        ):
            related.append(RelatedItem(item=db_item, similarity=result.score, match_type="SEMANTIC"))

    return related
```

---

## Step 3.3 — SOP Conflict Detection

SOP nằm trong Qdrant collection riêng `sop_documents`, không phải `source_type` trong `knowledge_items`. Trước khi so với worker knowledge, pipeline search SOP theo cùng `domain/entity/attribute`; nếu value khác cùng condition thì tạo `SopConflict` và chuyển item sang `ESCALATED`.

```python
class SopConflict(BaseModel):
    sop_chunk_id: str
    sop_value: str
    sop_condition: str | None
    similarity_score: float
    conflict_reason: str
```

Rule demo:
- Nếu SOP match cùng `entity AND attribute` và cùng/không rõ `condition`, value khác → `ESCALATED`.
- Nếu condition khác rõ ràng → không conflict, dùng cả hai như context có điều kiện.
- Agent không dùng item `ESCALATED` làm nguồn trả lời chính.

## Step 3.4 — Contradiction Detection (LLM-as-Judge)

Vector similarity cao ≠ contradiction. Cần LLM phân biệt supporting evidence vs actual conflict.

### Contradiction Judge Prompt

```
You are a knowledge conflict analyzer for a factory AI system.
Analyze whether these two operational facts CONTRADICT each other.

FACT A (existing knowledge):
Entity: {entity_a} | Attribute: {attribute_a} | Value: {value_a}
Condition: {condition_a} | Source: {source_type_a} | Confidence: {confidence_a}

FACT B (new claim):
Entity: {entity_b} | Attribute: {attribute_b} | Value: {value_b}
Condition: {condition_b} | Source: {source_type_b} | Confidence: {confidence_b}

IMPORTANT DISTINCTIONS:
- Different CONDITIONS = NOT a contradiction
  (e.g., "80°C for cotton" vs "75°C for polyester" → COMPATIBLE)
- Same condition, different values = CONTRADICTION
  (e.g., "dryer at 80°C" vs "dryer at 75°C" → CONFLICT)

Respond JSON:
{
  "is_contradiction": boolean,
  "contradiction_type": "DIRECT" | "CONDITIONAL" | "NONE",
  "explanation": "1-2 sentences",
  "recommended_action": "ACCEPT_NEW" | "KEEP_OLD" | "QUARANTINE_BOTH" | "ESCALATE",
  "reasoning": "why"
}
```

### Contradiction Types

| Type | Mô tả | Ví dụ |
|---|---|---|
| `DIRECT` | Cùng condition, giá trị khác | "dryer 80°C" vs "dryer 75°C" |
| `CONDITIONAL` | Khác condition → không mâu thuẫn | "80°C cotton" vs "75°C polyester" |
| `NONE` | Bổ sung nhau, không conflict | "dryer 80°C" + "check timing 30min" |

---

## Step 3.5 — Resolution Strategy

```python
async def resolve_conflict(
    new_item, existing_item, judgment, db, sop_conflict: SopConflict | None = None
) -> ResolutionResult:

    # Tier 0: SOP conflict → Escalate immediately
    if sop_conflict:
        await create_audit_log(db, new_item, action="ESCALATE_SOP_CONFLICT",
                               to_status="ESCALATED",
                               metadata=sop_conflict.model_dump())
        return await escalate(new_item, existing_item=None, db=db,
                              reason="Contradicts official SOP seeded stub")

    # Tier 1: No real conflict → support & accept
    if not judgment.is_contradiction or judgment.contradiction_type == "CONDITIONAL":
        if existing_item:
            await create_relation(db, new_item, existing_item, "SUPPORTS")
        return await auto_accept(new_item, db)

    # Tier 2: Safety-critical → Escalate immediately
    if new_item.structured_fact.get("domain") == "safety":
        return await escalate(new_item, existing_item, db,
                              reason="Safety-critical claim requires human review")

    # Tier 3: Trust-weighted decision
    new_weight = compute_trust_weight(new_item)
    old_weight = compute_trust_weight(existing_item)

    if new_weight > old_weight * 1.5:
        # New is significantly more trusted → accept new, supersede old
        await create_relation(db, new_item, existing_item, "SUPERSEDES")
        await update_status(existing_item, "SUPERSEDED", db,
                            note="Superseded by higher-confidence item")
        return await auto_accept(new_item, db)

    elif old_weight > new_weight * 1.5:
        # Old is significantly more trusted → reject new
        await create_relation(db, new_item, existing_item, "CONTRADICTS")
        return await reject(new_item, db,
                            reason="Contradicts higher-confidence existing knowledge")

    else:
        # Uncertain tie → quarantine both
        await create_relation(db, new_item, existing_item, "CONTRADICTS")
        await quarantine(existing_item, db, reason="Under conflict review")
        return await quarantine(new_item, db, reason="Contradicts existing knowledge")
```

---

## Step 3.6 — Trust Weight Computation

```python
def compute_trust_weight(item: KnowledgeItem) -> float:
    """
    Range: 0.0 to ~2.0 (không normalize cứng để phản ánh chênh lệch thực sự)
    """
    import math
    weight = item.confidence_score
    weight += math.log(1 + item.support_count) * 0.3   # logarithmic support bonus
    weight -= item.contradiction_count * 0.15            # contradiction penalty

    source_weights = {
        "WORKER_CORRECTION": +0.20,
        "WORKER_TEACHING":   +0.10,
        "WORKER_WARNING":    +0.10,
        "AMBIGUOUS":         -0.10,
    }
    weight += source_weights.get(item.source_type, 0)
    return max(0.0, weight)
```

---

## Step 3.7 — Auto-Accept Logic

```python
async def auto_accept(item: KnowledgeItem, db) -> ResolutionResult:
    can_auto_accept = (
        item.confidence_score >= 0.70
        and item.noise_score <= 0.35
        and item.contradiction_count == 0
        and item.structured_fact.get("domain") != "safety"  # safety luôn cần human
    )

    if can_auto_accept:
        await update_status(item, "VERIFIED", db)
        # Sync Qdrant payload
        await qdrant_client.set_payload(
            collection_name="tribal_knowledge",
            payload={"status": "VERIFIED"},
            points=[item.qdrant_vector_id],
        )
        return ResolutionResult(action="AUTO_ACCEPTED", new_status="VERIFIED")
    else:
        return await quarantine(item, db, reason="Confidence below auto-accept threshold")
```

---

## Step 3.8 — Support Counting (Crowd Confirmation)

Khi worker mới nói điều khớp với item đã có (similarity > 0.85 + cùng `entity AND attribute`), ghi vào `knowledge_support_evidence`. Chỉ promote khi evidence đến từ ít nhất 2 worker khác nhau, không tính trùng chính worker ban đầu.

```python
async def handle_supporting_evidence(new_item, existing_item, db):
    if new_item.worker_id == existing_item.worker_id:
        return await reject(new_item, db, reason="Duplicate from original worker")

    inserted = await insert_support_evidence_once(
        db,
        knowledge_item_id=existing_item.id,
        worker_id=new_item.worker_id,
        supporting_item_id=new_item.id,
    )
    if not inserted:
        return await reject(new_item, db, reason="Duplicate support from same worker")

    existing_item.support_count += 1
    existing_item.confidence_score = min(existing_item.confidence_score + 0.05, 1.0)

    # Worker trust score tăng khi được confirm
    existing_item.worker.trust_score = min(existing_item.worker.trust_score + 0.02, 1.0)

    distinct_supporters = await count_distinct_support_workers(db, existing_item.id)

    # Promote QUARANTINED → VERIFIED nếu đủ support từ worker khác nhau
    if (existing_item.status == "QUARANTINED"
            and distinct_supporters >= 2
            and existing_item.contradiction_count == 0):
        await auto_accept(existing_item, db)

    await db.commit()
    # Duplicate item → reject (không thêm vào KB)
    await reject(new_item, db, reason="Duplicate; support_count incremented on existing")
```

---

## Step 3.9 — Knowledge Review API

```
# Items cần human review
GET  /api/v1/knowledge/review?status=ESCALATED&status=QUARANTINED

# Human supervisor quyết định
PATCH /api/v1/knowledge/{id}/resolve
Body: {
  "decision": "VERIFY" | "REJECT" | "SUPERSEDE" | "QUARANTINE",
  "note": "...",
  "supervisor_id": "...",
  "applies_to_conflict_id": "optional"
}

# Conflict pairs (side-by-side view)
GET  /api/v1/knowledge/conflicts
→ [{item_a, item_b, similarity, contradiction_explanation, recommended_action}]

# Browse all items
GET  /api/v1/knowledge?status=VERIFIED&domain=welding&limit=20
```

---

## Step 3.10 — Anti-Poisoning Safeguards

1. **VERIFIED items không bị overwrite trực tiếp** — phải đi qua conflict pipeline, tạo `SUPERSEDES` relation, giữ lịch sử.
2. **Rollback capability** — mọi transition được ghi vào `knowledge_audit_logs` với timestamp + reason.
3. **SOP protection** — contradiction với SOP seeded stub luôn `ESCALATED`, không bao giờ auto-reject SOP.
4. **Rate limiting per worker** — max 10 auto-verified items/ngày tự động (chống coordinated injection); excess chuyển `QUARANTINED`.
5. **Confidence decay** — item không được retrieve trong 30 ngày → confidence giảm nhẹ và ghi audit log (tránh stale knowledge).

---

## Checklist Phase 3

- [ ] State machine chuyển PENDING → đúng trạng thái theo logic
- [ ] Chỉ PENDING items đi qua auto-verification pipeline
- [ ] SOP conflict dùng `SopConflict` từ `sop_documents`, không dùng `source_type=SOP_DOCUMENT`
- [ ] Qdrant 2-stage search tìm đúng related items
- [ ] LLM judge phân biệt DIRECT vs CONDITIONAL contradiction
- [ ] 3-tier resolution: no-conflict / SOP+safety escalate / trust-weighted
- [ ] Trust weight = confidence + log(support) - contradiction_penalty + source_bonus
- [ ] Auto-accept threshold 0.70 hoạt động
- [ ] Support counting: QUARANTINED → VERIFIED khi ≥2 workers khác nhau confirm
- [ ] `PATCH /knowledge/{id}/resolve` hỗ trợ VERIFY/REJECT/SUPERSEDE/QUARANTINE
- [ ] Anti-poisoning: SOP không thể bị auto-reject
- [ ] Audit log ghi mọi transition và trust adjustment
- [ ] Test: "dryer 80°C" vs "dryer 75°C" → cả 2 QUARANTINED
- [ ] Test: worker nói dryer 75°C, SOP seed ghi 78°C → item ESCALATED
- [ ] Test: senior worker correct junior → auto-accept new item
