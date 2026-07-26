# Email Assistant

**An agentic AI system that turns an inbox into a queryable knowledge base.** Ask questions in natural language; the assistant plans, routes to the right model tier, calls specialized retrieval and SQL tools, and returns grounded, source-attributed answers.

---

## Overview

A **LangGraph-orchestrated agent** that reasons about each query, routes it to the cheapest capable model tier, calls specialized retrieval and read-only SQL tools, and grounds every answer in retrieved evidence — with a built-in evaluation harness that scores whether it actually did.

Three things make it more than a chatbot over search:

- **Engineered answer quality** — hybrid retrieval (vector + BM25, query expansion, cross-encoder reranking) plus an LLM-as-judge suite that turns grounding and faithfulness into numbers you can track.
- **Cost that scales with difficulty** — a zero-latency classifier routes each query across three Gemini tiers, so trivial queries stay cheap and hard ones get the reasoning they need.
- **Safe by construction** — the SQL tool is read-only behind a defense-in-depth guardrail layer, so the agent reasons over relational data without ever being able to mutate it.

The system is a modular, layered architecture. Some layers — live email ingestion, CI/CD, and cloud deployment — are scaffolded extension points rather than fully built, so the core (agent, retrieval, SQL, persistence, evaluation) runs end-to-end today.

---

## Architecture

![Architecture](assets/images/email-system-architecture.svg)

The diagram is the target architecture. A few components are still scaffolding rather than fully wired:

- **Streamlit app** shares the CLI's core — tiered model routing, the same semantic-search + read-only SQL tools, and `src.*` imports. A few UI-only concerns (dev-mode tool logging) surface on the server console rather than in the browser.
- **Redis** has a working client and `CacheService` wrapper, but caching is not yet on the request path.
- **Rate limiting** exists as a tokens-per-minute throttle in offline ingestion, not as a runtime guard.
- **Planned:** CI/CD, container registry, cloud deployment, live inbox ingestion, and continuous-improvement feedback loops.

---

## Core Features

- **Hybrid semantic retrieval** — query expansion → OpenAI embeddings → Chroma vector search fused with BM25 lexical retrieval → cross-encoder reranking, returning the top grounded chunks with source IDs.
- **Guarded read-only SQL** — the agent writes `SELECT` / `WITH` queries against a normalized email schema; a validation layer rejects DML/DDL and dangerous functions, and every query runs inside a `READ ONLY` transaction with a hard row cap.
- **Adaptive model routing** — heuristic complexity classification (keywords + regex, no extra LLM call) routes each query to the cheapest model tier that can handle it, erring upward when uncertain.
- **Persistent chat threads** — threads and message history are stored in PostgreSQL, with recent-context windowing for conversational continuity.
- **Built-in evaluation** — an LLM-as-judge scores retrieval quality (context relevance, faithfulness, answer relevance, completeness) and agent behavior (response quality, factual grounding, tool appropriateness, conciseness).
- **Two interfaces** — a Rich-powered CLI and a Streamlit chat UI.

---

## Project Structure

```text
.
├── src/
│   ├── main.py                  # CLI chat entrypoint + LangGraph agent
│   ├── lib/                     # router, pipeline, db, cache, prompts, evaluator, ingestion, utils
│   ├── models/                  # SQLAlchemy data models
│   ├── services/                # thread and cache services
│   └── tools/                   # semantic search, SQL, metadata filtering, eval tools
├── ui/
│   └── streamlit_app.py         # Streamlit UI (prototype over the core stack)
├── scripts/
│   ├── migrate_data.py          # load normalized email data into Postgres
│   └── run_eval.py              # run RAG and agent evaluation suites
├── migrations/                  # Alembic migrations
├── tests/                       # unit, integration, and eval tests
├── assets/images/               # architecture diagram
├── docker-compose.yml           # local Postgres (pgvector) + Redis
├── pyproject.toml               # project metadata and dependencies (uv)
└── .env.example                 # required environment variables
```

---

## Prerequisites

- Python `3.14+`
- `uv`
- Docker and Docker Compose
- API access for:
  - Google Gemini (`GOOGLE_API_KEY`)
  - OpenAI embeddings (`OPENAI_API_KEY`)
  - Chroma Cloud (`CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`)

## Setup

### 1. Clone the repository

```bash
git clone git@github.com:Hrithik450/email-assistant.git
cd email-assistant
```

### 2. Create your environment file

```bash
cp .env.example .env
```

Then update `.env` with real credentials:

```env
GOOGLE_API_KEY="your-google-api-key"
OPENAI_API_KEY="your-openai-api-key"
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/email_assistant"
REDIS_URL="redis://localhost:6379"
CHROMA_API_KEY="your-chroma-api-key"
CHROMA_TENANT="your-chroma-tenant-id"
CHROMA_DATABASE="your-chroma-database-name"
EMAIL_JSONL_GDRIVE_ID="your-gdrive-file-id"
DEV_MODE="0 or 1"
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Start local infrastructure

```bash
docker compose up -d
```

This starts:

- PostgreSQL with `pgvector` on `localhost:5433`
- Redis on `localhost:6379`

### 5. Run database migrations

```bash
uv run alembic upgrade head
```

### 6. Prepare data

The raw data fetched from the google drive will be stored into here:

```text
src/lib/data/raw_mails.jsonl
```

After fetching the raw data, run the normalizer to produce the normalized dataset:

```bash
uv run python src/lib/normalize.py
```

This writes normalized email records to:

```text
src/lib/data/norm_data.jsonl
```

To load normalized email records into PostgreSQL, run the migration script, which reads from:

```text
src/lib/data/norm_data.jsonl
```

```bash
uv run python scripts/migrate_data.py
```

> Vector embeddings are expected to live in a Chroma Cloud collection (`organization_data`); the app connects to it at runtime rather than building the index locally.

## Running the App

### CLI chat

```bash
uv run python src/main.py
```

### Streamlit UI

```bash
uv run streamlit run ui/streamlit_app.py
```

The Streamlit app provides a chat interface over the same retrieval/tooling core. See the architecture notes above for how it currently differs from the CLI agent.

## Testing

Run the full pytest suite:

```bash
uv run pytest
```

Run only unit tests:

```bash
uv run pytest -m unit
```

Run integration tests:

```bash
uv run pytest -m integration
```

Notes:

- Integration tests require a reachable PostgreSQL instance.
- Redis-backed tests require `REDIS_URL`.
- Some tests expect sample data under `src/lib/data/`.

## Evaluation

Run both RAG and agent evaluation suites:

```bash
uv run python scripts/run_eval.py
```

Run only RAG evaluation:

```bash
uv run python scripts/run_eval.py --rag
```

Run only agent evaluation:

```bash
uv run python scripts/run_eval.py --agent
```

Set a custom pass threshold:

```bash
uv run python scripts/run_eval.py --threshold 3.5
```

## Current Stack

- **Orchestration:** LangGraph, LangChain
- **Models:** Google Gemini (chat), OpenAI (embeddings & summarization)
- **Retrieval:** ChromaDB, BM25 (`rank-bm25`), cross-encoder reranking (`sentence-transformers`)
- **Data:** PostgreSQL + `pgvector`, Redis, Polars
- **Interfaces:** Rich CLI, Streamlit
- **Tooling:** Pytest, Alembic, `uv`

## Notes

- Dependency management is handled through `pyproject.toml` and `uv.lock`, not `requirements.txt`.
- Local infrastructure runs via Docker Compose.

## License

This project is intended for research, experimentation, and enterprise knowledge-assistant development.
</content>