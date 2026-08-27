import os
import numpy as np
from langchain.tools import tool
from sentence_transformers import CrossEncoder

from src.lib.db import get_pool
from src.lib.gemini_pool import get_gemini_key, mark_key_exhausted
from src.lib.embeddings import get_embeddings
from src.lib.logger import get_logger, log_tool_call
from src.lib.utils import EMBEDDING_DIM

logger = get_logger(__name__)

_cross_encoder: CrossEncoder | None = None

def _get_cross_encoder() -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder

def _to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"

def _fts_search(query: str, n_results: int = 50) -> list[tuple[str, str | None, float]]:
    sql = """
        SELECT content, gmail_email_id,
               ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', %s)) AS bm25_score
        FROM email_embedding
        WHERE to_tsvector('english', content) @@ websearch_to_tsquery('english', %s)
        ORDER BY bm25_score DESC
        LIMIT %s
    """
    results = []
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (query, query, n_results))
            results = [(content, eid, float(score)) for content, eid, score in cur.fetchall()]
    return results

def _vector_search(query_embedding: list[float], n_results: int = 50) -> list[tuple[str, str | None, float]]:
    sql = f"""
        SELECT content, gmail_email_id,
               1 - (embedding::halfvec({EMBEDDING_DIM}) <=> %s::halfvec({EMBEDDING_DIM})) AS sim
        FROM email_embedding
        ORDER BY embedding::halfvec({EMBEDDING_DIM}) <=> %s::halfvec({EMBEDDING_DIM})
        LIMIT %s
    """
    results = []
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            literal = _to_vector_literal(query_embedding)
            cur.execute(sql, (literal, literal, n_results))
            results = [(content, eid, float(sim)) for content, eid, sim in cur.fetchall()]
    return results

def _fetch_email_sources(email_ids: list[str]) -> dict[str, dict]:
    ids = [e for e in dict.fromkeys(email_ids) if e]
    if not ids:
        return {}

    try:
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
        logger.warning("Source enrichment failed: %s", exc)
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
    """Performs optimized Hybrid Search (FTS + Vector) with Cross-Encoding re-ranking.

    Args:
        query: The natural language query.
    """
    log_tool_call("semantic_search_tool", query)

    # 1. Embed query (fast API call, no query expansion LLM latency)
    query_embedding = None
    last_err = None
    for _ in range(10):
        key = get_gemini_key("embedding")
        try:
            query_embedding = get_embeddings("RETRIEVAL_QUERY", key=key).embed_query(query)
            break
        except Exception as exc:
            err_str = str(exc)
            if any(e in err_str for e in ["429", "503", "401", "403", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND"]):
                logger.warning("Gemini key exhausted for embeddings, marking 60s cooldown...")
                mark_key_exhausted(key, cooldown_secs=60)
                last_err = exc
                continue
            logger.warning("Embedding failed: %s", exc)
            return "Error: could not generate query embeddings."
            
    if not query_embedding:
        logger.warning("All keys exhausted for embeddings. Last error: %s", last_err)
        return "Error: Vector embeddings are currently unavailable due to rate limits."

    # 2. Run searches in parallel or sequentially (fast)
    try:
        vector_results = _vector_search(query_embedding, n_results=150)
    except Exception as exc:
        logger.warning("pgvector query failed: %s", exc)
        vector_results = []

    try:
        fts_results = _fts_search(query, n_results=150)
    except Exception as exc:
        logger.warning("FTS query failed: %s", exc)
        fts_results = []

    # 3. Combine scores
    candidate_map = {}
    
    for fts_doc, fts_eid, fts_score in fts_results:
        candidate_map[fts_doc] = {
            "email_id": fts_eid,
            "score": candidate_map.get(fts_doc, {}).get("score", 0) + fts_score,
        }

    for v_doc, v_eid, v_sim in vector_results:
        candidate_map[v_doc] = {
            "email_id": v_eid,
            "score": candidate_map.get(v_doc, {}).get("score", 0) + (v_sim * 10),
        }

    if not candidate_map:
        return "No relevant documents found."

    # 4. Limit Cross-Encoder to top 100 to increase recall
    top_candidates = sorted(
        candidate_map.items(), key=lambda x: x[1]["score"], reverse=True
    )[:100]

    pairs = [[query, text] for text, _ in top_candidates]
    cross_scores = _get_cross_encoder().predict(pairs)

    # Return top 50 highly relevant chunks to the LLM context
    final_ranked = sorted(
        zip(cross_scores, top_candidates), key=lambda x: x[0], reverse=True
    )[:50]

    sources = _fetch_email_sources([info["email_id"] for _, (_, info) in final_ranked])

    output = []
    for rel_score, (text, info) in final_ranked:
        eid = info["email_id"]
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
