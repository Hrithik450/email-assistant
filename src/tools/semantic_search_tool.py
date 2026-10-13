import os
import numpy as np
from langchain.tools import tool
from sentence_transformers import CrossEncoder

from src.lib.logger import get_logger, log_tool_call
from src.lib.pipeline import get_chroma_collection
from src.lib.embeddings import embed_query
from src.lib.utils import CHROMA_COLLECTION_NAME

logger = get_logger(__name__)

_cross_encoder: CrossEncoder | None = None


def _get_cross_encoder() -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


def _fetch_email_sources(email_ids: list[str]) -> dict[str, dict]:
    """Fetch sender / subject / date for gmail email ids from Postgres if available."""
    ids = [e for e in dict.fromkeys(email_ids) if e]
    if not ids:
        return {}

    try:
        from src.lib.db import get_pool
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.gmail_email_id,
                           COALESCE(NULLIF(u.display_name, ''), u.email) AS sender,
                           e.subject,
                           e.sent_at
                    FROM email e
                    LEFT JOIN email_user u ON u.id = e.sender_id
                    WHERE e.gmail_email_id = ANY(%s)
                    """,
                    (ids,),
                )
                rows = cur.fetchall()
    except Exception as exc:
        logger.debug("Source enrichment skipped/failed: %s", exc)
        return {}

    result: dict[str, dict] = {}
    for gmail_id, sender, subject, sent_at in rows:
        result[gmail_id] = {
            "sender": sender or "Unknown sender",
            "subject": subject or "(no subject)",
            "date": sent_at.strftime("%Y-%m-%d") if sent_at else "unknown date",
        }
    return result


@tool("semantic_search_tool", parse_docstring=True)
def semantic_search_tool(query: str) -> str:
    """Performs semantic search over the Chroma vector database with Cross-Encoder re-ranking.

    Args:
        query: The natural language query.
    """
    log_tool_call("semantic_search_tool", query)

    # 1. Access ChromaDB collection
    collection = get_chroma_collection(CHROMA_COLLECTION_NAME)
    if collection is None:
        return "Error: ChromaDB vector store is currently unavailable."

    # 2. Generate 3072-dimension query embedding using Gemini
    try:
        query_embedding = embed_query(query, task_type="RETRIEVAL_QUERY")
    except Exception as exc:
        logger.warning("Gemini embedding failed: %s", exc)
        return "Error: Could not generate vector embeddings for query."

    # 3. Query ChromaDB vector database
    try:
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=50,
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return f"Error querying ChromaDB: {exc}"

    documents = search_results.get("documents", [[]])[0]
    metadatas = search_results.get("metadatas", [[]])[0]
    distances = search_results.get("distances", [[]])[0]

    if not documents:
        return "No relevant documents found."

    # 4. Prepare candidates for Cross-Encoder re-ranking
    candidates = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        eid = meta.get("email_id") if isinstance(meta, dict) else None
        candidates.append((doc, eid, dist))

    # Re-rank top candidates using Cross-Encoder
    top_candidates = candidates[:30]
    pairs = [[query, doc] for doc, _, _ in top_candidates]
    try:
        cross_scores = _get_cross_encoder().predict(pairs)
        ranked = sorted(
            zip(cross_scores, top_candidates), key=lambda x: x[0], reverse=True
        )[:20]
    except Exception as exc:
        logger.warning("Cross-encoder reranking failed, falling back to vector distance: %s", exc)
        ranked = [(1.0 / (1.0 + dist), cand) for cand in top_candidates]

    email_ids = [cand[1] for _, cand in ranked if cand[1]]
    sources = _fetch_email_sources(email_ids)

    # 5. Format output
    output = []
    for score, (text, eid, _) in ranked:
        src = sources.get(eid)
        if src:
            header = (
                f"[Source] From: {src['sender']} | "
                f"Subject: {src['subject']} | Date: {src['date']} | id: {eid}\n"
            )
        elif eid:
            header = f"[id: {eid}]\n"
        else:
            header = ""
        output.append(f"{header}{text}")

    return "\n\n---\n\n".join(output)
