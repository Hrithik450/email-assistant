# Email Assistant

**An agentic AI system that turns an inbox into a queryable knowledge base.** Ask questions in natural language; the assistant plans, routes to the right model tier, calls specialized retrieval and SQL tools, and returns grounded, source-attributed answers.

---

## Overview

A **LangGraph-orchestrated agent** that reasons about each query, routes it to the cheapest capable model tier, calls specialized retrieval and read-only SQL tools, and grounds every answer in retrieved evidence — with a built-in evaluation harness that scores whether it actually did.

Three things make it more than a chatbot over search:

- **Engineered answer quality** — hybrid retrieval (vector + BM25, query expansion, cross-encoder reranking) plus an LLM-as-judge suite that turns grounding and faithfulness into numbers you can track.
- **Cost that scales with difficulty** — a zero-latency classifier routes each query across three Gemini tiers, so trivial queries stay cheap and hard ones get the reasoning they need.
- **Safe by construction** — the SQL tool is read-only behind a defense-in-depth guardrail layer, so the agent reasons over relational data without ever being able to mutate it.

The system is a modular, layered architecture. Some layers — live email ingestion and CI/CD — are scaffolded extension points rather than fully built, so the core (agent, retrieval, SQL, persistence, evaluation) runs end-to-end today. Everything runs on **Google Gemini** (chat, embeddings, and offline summarization) with **self-hosted pgvector** for vector search — no third-party vector service required.

---

## Architecture

![Architecture](assets/images/email-system-architecture.svg)

The diagram is the target architecture. A few components are still scaffolding rather than fully wired:

- **Streamlit app** shares the CLI's core — tiered model routing, the same semantic-search + read-only SQL tools, and `src.*` imports. A few UI-only concerns (dev-mode tool logging) surface on the server console rather than in the browser.
- **Redis** has a working client and `CacheService` wrapper, but caching is not yet on the request path.
- **Rate limiting** exists as a tokens-per-minute throttle in offline ingestion, not as a runtime guard.
- **Planned:** CI/CD, container registry, live inbox ingestion, and continuous-improvement feedback loops.

---

## Core Features

- **Hybrid semantic retrieval** — query expansion → Gemini embeddings (`gemini-embedding-001`) → pgvector cosine search fused with BM25 lexical retrieval → cross-encoder reranking, returning the top grounded chunks with source IDs.
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
│   ├── lib/                     # router, embeddings, db, cache, prompts, evaluator, ingestion, utils
│   ├── models/                  # SQLAlchemy data models
│   ├── services/                # thread and cache services
│   └── tools/                   # semantic search, SQL, metadata filtering, eval tools
├── ui/
│   └── streamlit_app.py         # Streamlit UI (prototype over the core stack)
├── scripts/
│   ├── migrate_data.py                 # load normalized email data into Postgres
│   ├── migrate_chroma_to_pgvector.py   # one-time: export Chroma docs → build pgvector index
│   ├── build_vector_index.py           # (re)build the pgvector index from vector_docs.jsonl
│   └── run_eval.py                     # run RAG and agent evaluation suites
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
- A **Google Gemini API key** (`GOOGLE_API_KEY`) — used for chat, embeddings, and summarization.

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

Then update `.env` with real values:

```env
GOOGLE_API_KEY="your-google-api-key"
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/email_assistant"
REDIS_URL="redis://localhost:6379"
DEV_MODE="0"
```

> The Streamlit UI reads the same values from `.streamlit/secrets.toml` (`GOOGLE_API_KEY`, `DATABASE_URL`, `REDIS_URL`). Keep the two files in sync.

### 3. Install dependencies

```bash
uv sync
```

### 4. Start local infrastructure

```bash
docker compose up -d
```

This starts:

- PostgreSQL with `pgvector` on `localhost:5433` (image `pgvector/pgvector:pg16`, which ships the `vector` + `halfvec` types)
- Redis on `localhost:6379`

### 5. Run database migrations

```bash
uv run alembic upgrade head
```

This creates every table, including `email_embedding` (a `vector(3072)` column with an HNSW index over its `halfvec(3072)` cast).

### 6. Load relational email data

Normalize the raw dataset, then load it into Postgres:

```bash
uv run python src/lib/normalize.py       # writes src/lib/data/norm_data.jsonl
uv run python scripts/migrate_data.py    # loads norm_data.jsonl into Postgres
```

### 7. Build the vector index (pgvector + Gemini)

Vector documents are LLM-generated thread summaries. There are two ways to populate `email_embedding`:

**a) One-time migration from an existing Chroma Cloud collection.** The document text lives only in Chroma, so export it once, then re-embed with Gemini. Chroma is no longer a dependency, so reinstall it temporarily just for this step:

```bash
uv pip install chromadb==1.5.9
# set CHROMA_API_KEY / CHROMA_TENANT / CHROMA_DATABASE in your environment
uv run python scripts/migrate_chroma_to_pgvector.py
```

This writes a durable backup to `src/lib/data/vector_docs.jsonl`, then embeds every document with `gemini-embedding-001` and fills `email_embedding`. Afterwards you can uninstall Chroma again (`uv pip uninstall chromadb`) — it is never needed at runtime.

**b) Rebuild anytime from the durable backup** (no Chroma required):

```bash
uv run python scripts/build_vector_index.py
```

The build is idempotent and resumable — already-embedded documents are skipped, so a re-run after a failure continues where it stopped.

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

---

## Deploying on EC2 (self-hosted, Streamlit + local pgvector)

Everything runs on a single instance: Postgres (pgvector) and Redis via Docker Compose, with Streamlit connecting over `localhost`.

**On the EC2 box (Amazon Linux 2023 or Ubuntu):**

1. **Install Docker + Compose plugin, `uv`, and clone the repo.**

   ```bash
   # Docker (Ubuntu)
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker "$USER" && newgrp docker
   # uv
   curl -LsSf https://astral.sh/uv/install.sh | sh
   git clone https://github.com/Hrithik450/email-assistant.git
   cd email-assistant
   ```

2. **Create config** — `.env` (CLI) and `.streamlit/secrets.toml` (UI), both pointing at the instance-local Postgres:

   ```env
   GOOGLE_API_KEY="your-google-api-key"
   DATABASE_URL="postgresql://postgres:postgres@localhost:5433/email_assistant"
   REDIS_URL="redis://localhost:6379"
   ```

3. **Start infrastructure and migrate:**

   ```bash
   docker compose up -d
   uv sync
   uv run alembic upgrade head
   ```

4. **Load data** (steps 6–7 above): relational data via `migrate_data.py`, then the vector index via `migrate_chroma_to_pgvector.py` (once) or `build_vector_index.py`.

5. **Run Streamlit bound to all interfaces:**

   ```bash
   uv run streamlit run ui/streamlit_app.py --server.port 8501 --server.address 0.0.0.0
   ```

**Making it reachable — pick one:**

- **Quick (dev):** open port **8501** in the instance's security group and visit `http://<ec2-public-ip>:8501`.
- **Production:** run Streamlit under **systemd** (auto-restart on boot/crash) behind an **nginx** reverse proxy on 80/443 with TLS; open only 80/443.

<details>
<summary>Sample <code>systemd</code> unit — <code>/etc/systemd/system/email-assistant.service</code></summary>

```ini
[Unit]
Description=Email Assistant (Streamlit)
After=network.target docker.service
Requires=docker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/email-assistant
ExecStart=/home/ubuntu/.local/bin/uv run streamlit run ui/streamlit_app.py \
  --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-assistant
```

</details>

<details>
<summary>Sample nginx reverse proxy (WebSocket-aware) — <code>/etc/nginx/sites-available/email-assistant</code></summary>

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Streamlit uses WebSockets for live updates
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

Then add TLS with `sudo certbot --nginx -d your-domain.com`.

</details>

> Postgres and Redis stay bound to the instance (never expose 5433/6379 publicly). The Docker volume `pgdata` persists your embeddings across restarts, so the one-time index build survives reboots.

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
- **Models:** Google Gemini — chat (tiered `gemini-2.5`/`3.5` routing), embeddings (`gemini-embedding-001`), and offline summarization (`gemini-2.5-flash-lite`)
- **Retrieval:** PostgreSQL + `pgvector` (HNSW over `halfvec`), BM25 (`rank-bm25`), cross-encoder reranking (`sentence-transformers`)
- **Data:** PostgreSQL, Redis, Polars
- **Interfaces:** Rich CLI, Streamlit
- **Tooling:** Pytest, Alembic, `uv`

## Notes

- Dependency management is handled through `pyproject.toml` and `uv.lock`, not `requirements.txt`.
- Local infrastructure runs via Docker Compose.

## License

This project is intended for research, experimentation, and enterprise knowledge-assistant development.
