# Email Assistant

An AI-powered email knowledge assistant for searching, analyzing, and answering questions over email data using semantic retrieval, SQL-based reasoning, and a LangGraph agent.

## Overview

This project combines:

- A LangGraph-based agent with model routing
- Hybrid retrieval over email content using ChromaDB, BM25, and reranking
- Read-only relational querying over PostgreSQL email data
- Thread/message persistence with PostgreSQL and Redis-backed caching
- Evaluation utilities for both retrieval and agent behavior

## Architecture

![Architecture](assets/images/email-system-architecture.svg)

## Project Structure

```text
.
├── src/
│   ├── main.py                  # CLI chat entrypoint
│   ├── lib/                     # prompts, pipeline, DB, routing, evaluation
│   ├── models/                  # data models
│   ├── services/                # thread and cache services
│   └── tools/                   # semantic search, SQL, and eval tools
├── ui/
│   └── streamlit_app.py         # Streamlit UI
├── scripts/
│   ├── migrate_data.py          # load normalized email data into Postgres
│   └── run_eval.py              # run RAG and agent evaluation suites
├── migrations/                  # Alembic migrations
├── tests/                       # unit, integration, and eval tests
├── assets/images/               # architecture diagrams
├── docker-compose.yml           # local Postgres + Redis
├── pyproject.toml               # project metadata and dependencies
└── .env.example                 # required environment variables
```

## Core Features

- Hybrid semantic retrieval using ChromaDB, BM25, query expansion, and fine tuned cross-encoder reranking
- Read-only SQL analysis over normalized email tables
- Model-tier routing for simple, standard, and complex queries
- Persistent chat threads and message history
- Evaluation tooling for retrieval quality and agent grounding
- Streamlit UI and CLI chat entrypoints

## Data Model

The database separates application users from people found inside email data.

Application domain:

- `user`
- `thread`
- `thread_messages`

Email domain:

- `email_user`
- `email_thread`
- `email`
- `recipient`
- `attachment`
- `email_label`

This separation is especially important when querying through `relational_query_tool`.

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
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/re_assistant"
REDIS_URL="redis://localhost:6379"
CHROMA_API_KEY="your-chroma-api-key"
CHROMA_TENANT="your-chroma-tenant-id"
CHROMA_DATABASE="your-chroma-database-name"
EMAIL_JSONL_GDRIVE_ID="your-gdrive-file-id"
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

For local CLI usage, the pipeline expects a normalized JSONL file at:

```text
src/lib/data/norm_emails.jsonl
```

To load normalized email records into PostgreSQL:

```bash
uv run python scripts/migrate_data.py
```

The migration script reads from:

```text
src/lib/data/norm_data.jsonl
```

## Running the App

### CLI chat

```bash
uv run python src/main.py
```

### Streamlit UI

```bash
uv run streamlit run ui/streamlit_app.py
```

The Streamlit app is intended to provide a chat interface over the same agent/tooling stack.

## Tools in the Agent

### `semantic_search_tool`

Searches email content using:

- Query expansion
- OpenAI embeddings
- Chroma vector search
- BM25 lexical retrieval
- Cross-encoder reranking

### `relational_query_tool`

Executes read-only `SELECT` and `WITH` SQL queries against PostgreSQL with safety checks that reject write or destructive statements.

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

- LangGraph
- LangChain
- Google Gemini
- OpenAI Embeddings
- ChromaDB
- PostgreSQL + pgvector
- Redis
- Polars
- Streamlit
- Pytest
- Alembic

## Notes

- Dependency management is handled through `pyproject.toml` and `uv.lock`, not `requirements.txt`.
- Local infrastructure is expected to run via Docker Compose.

## License

This project is intended for research, experimentation, and enterprise knowledge assistant development.