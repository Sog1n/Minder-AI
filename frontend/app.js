const api = {
  workers: "/api/v1/workers",
  ingest: "/api/v1/conversations/ingest",
  knowledge: "/api/v1/knowledge",
  conflicts: "/api/v1/knowledge/conflicts",
  metrics: "/api/v1/metrics/dashboard",
  agent: "/api/v1/agent/query",
};

const $ = (id) => document.getElementById(id);

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status}: ${await response.text()}`);
  }
  return response.json();
}

function formatPercent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

async function loadWorkers() {
  const workers = await jsonFetch(api.workers);
  $("workerSelect").innerHTML = workers
    .map((worker) => `<option value="${worker.id}">${worker.name} (${worker.department})</option>`)
    .join("");
}

function renderFact(item) {
  const fact = item.structured_fact;
  return `
    <div class="item">
      <strong>${fact.entity || "unknown"} / ${fact.attribute || "unknown"}</strong>
      <span class="badge ${item.status}">${item.status}</span>
      <p>${item.raw_text}</p>
      <p>Value: ${fact.value || ""} ${fact.unit || ""} | Confidence: ${item.confidence_score.toFixed(2)}</p>
      <div class="actions">
        <button class="secondary" onclick="resolveItem('${item.id}', 'VERIFY')">Verify</button>
        <button class="secondary" onclick="resolveItem('${item.id}', 'REJECT')">Reject</button>
        <button class="secondary" onclick="resolveItem('${item.id}', 'QUARANTINE')">Quarantine</button>
      </div>
    </div>
  `;
}

async function loadKnowledge() {
  const status = $("statusFilter").value;
  const url = status ? `${api.knowledge}?status=${status}&limit=50` : `${api.knowledge}?limit=50`;
  const data = await jsonFetch(url);
  $("knowledgeList").innerHTML = data.items.length ? data.items.map(renderFact).join("") : "<p>No knowledge items yet.</p>";
}

async function loadConflicts() {
  const data = await jsonFetch(api.conflicts);
  $("conflictList").innerHTML = data.conflicts.length
    ? data.conflicts
        .map(
          (conflict) => `
        <div class="item">
          <strong>${conflict.recommended_action}</strong>
          <p>${conflict.contradiction_explanation}</p>
          <p>A: ${conflict.item_a.structured_fact.value} | B: ${conflict.item_b.structured_fact.value}</p>
        </div>
      `,
        )
        .join("")
    : "<p>No conflicts detected.</p>";
}

async function loadMetrics() {
  const data = await jsonFetch(api.metrics);
  const today = data.today;
  const metrics = [
    ["Correction Rate", formatPercent(today.correction_rate)],
    ["KB Coverage", formatPercent(today.kbc_score)],
    ["Acceptance Rate", formatPercent(today.kar)],
    ["Utilization Rate", formatPercent(today.kur)],
    ["Verified", today.verified_count],
    ["Needs Review", (data.pending_review.quarantined_count || 0) + (data.pending_review.escalated_count || 0)],
  ];
  $("metrics").innerHTML = metrics.map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

async function refreshAll() {
  await Promise.all([loadKnowledge(), loadConflicts(), loadMetrics()]);
}

async function submitConversation() {
  const payload = {
    worker_id: $("workerSelect").value,
    transcript: $("transcript").value,
  };
  const response = await jsonFetch(api.ingest, { method: "POST", body: JSON.stringify(payload) });
  $("conversationStatus").textContent = JSON.stringify(response, null, 2);
  setTimeout(async () => {
    const status = await jsonFetch(`/api/v1/conversations/${response.conversation_id}/status`);
    $("conversationStatus").textContent = JSON.stringify(status, null, 2);
    await refreshAll();
  }, 700);
}

async function runQuery() {
  const response = await jsonFetch(api.agent, {
    method: "POST",
    body: JSON.stringify({
      worker_id: $("workerSelect").value,
      query: $("transcript").value,
    }),
  });
  $("agentResponse").textContent = JSON.stringify(response, null, 2);
  await refreshAll();
}

async function resolveItem(id, decision) {
  await jsonFetch(`${api.knowledge}/${id}/resolve`, {
    method: "PATCH",
    body: JSON.stringify({
      decision,
      supervisor_id: "demo_supervisor",
      note: `Manual ${decision.toLowerCase()} from dashboard`,
    }),
  });
  await refreshAll();
}

window.resolveItem = resolveItem;

$("submitConversation").addEventListener("click", submitConversation);
$("runQuery").addEventListener("click", runQuery);
$("refresh").addEventListener("click", refreshAll);
$("statusFilter").addEventListener("change", loadKnowledge);

loadWorkers().then(refreshAll).catch((error) => {
  $("conversationStatus").textContent = error.message;
});

