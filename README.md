# Minder AI Knowledge System

Technical demo and production-oriented design for learning factory tribal knowledge from transcripts.

## Runtime Modes

The app supports two modes:

- `LLM_MODE=demo`: offline deterministic fallback for local demo/tests. No API key required.
- `LLM_MODE=openai`: real LLM-backed pipeline using OpenAI APIs.

Set `.env`:

```env
LLM_MODE=openai
OPENAI_API_KEY=sk-...
OPENAI_EXTRACTION_MODEL=gpt-4o
OPENAI_JUDGE_MODEL=gpt-4o-mini
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

## Real LLM Pipeline

1. `OpenAIExtractor` uses Structured Outputs to convert transcript text into 0-5 structured operational facts.
2. Noise/confidence scoring remains deterministic and auditable.
3. SOP conflict is checked before worker conflict; SOP remains official.
4. `OpenAIConflictJudge` uses Structured Outputs to classify worker-vs-worker conflicts.
5. `OpenAIEmbeddingSearch` uses `text-embedding-3-small` for SOP and `VERIFIED` tribal retrieval.
6. `OpenAIAgentGenerator` answers with SOP-first policy and cites field knowledge only as augmentation.

The deterministic extractor/judge/search/answer generator are intentionally kept as test doubles, not production logic. In a production deployment, the in-memory embedding index should be replaced by Qdrant using the same vector-search interface.

## Run

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Dashboard: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

## Verify

```bash
python -m compileall app scripts tests
python -m pytest -q
```
