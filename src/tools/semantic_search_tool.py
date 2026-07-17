import os

import numpy as np
from langchain.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import OpenAIEmbeddings
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from src.lib.logger import get_logger, log_tool_call
from src.lib.utils import EMBEDDING_MODEL_NAME

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy initialization — all heavy resources deferred to first use
# ---------------------------------------------------------------------------

_search_state: dict | None = None
_cross_encoder: CrossEncoder | None = None
_generate_queries = None
_embedding_model = None


def _init_search():
    global _search_state
    if _search_state is not None:
        return _search_state

    from src.lib.pipeline import chroma_collection

    if chroma_collection is None:
        _search_state = {"ready": False}
        return _search_state

    all_chroma = chroma_collection.get(include=["documents", "metadatas"])
    documents = all_chroma["documents"]
    metadatas = all_chroma["metadatas"]
    tokenized_docs = [doc.lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized_docs)

    _search_state = {
        "ready": True,
        "collection": chroma_collection,
        "documents": documents,
        "metadatas": metadatas,
        "bm25": bm25,
    }
    return _search_state


def _get_cross_encoder() -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _cross_encoder


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = OpenAIEmbeddings(
            model=EMBEDDING_MODEL_NAME, api_key=os.environ.get("OPENAI_API_KEY", "")
        )
    return _embedding_model


def _get_query_expander():
    global _generate_queries
    if _generate_queries is not None:
        return _generate_queries

    template = """You are an AI language model assistant. Your task is to generate 3
different versions of the given user question to retrieve relevant documents from a vector
database. By generating multiple perspectives on the user question, your goal is to help
the user overcome some of the limitations of the distance-based similarity search.
Provide these alternative questions separated by newlines. Original question: {question}"""

    prompt_perspectives = ChatPromptTemplate.from_template(template)

    _generate_queries = (
        prompt_perspectives
        | ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0,
            max_retries=2,
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        )
        | StrOutputParser()
        | (lambda x: x.split("\n"))
    )
    return _generate_queries


def _fetch_email_sources(email_ids: list[str]) -> dict[str, dict]:
    """Fetch sender / subject / date for gmail email ids from Postgres.

    Returns a map keyed by gmail_email_id. Missing ids are simply absent.
    Never raises — attribution is best-effort and must not break search.
    """
    ids = [e for e in dict.fromkeys(email_ids) if e]
    if not ids:
        return {}

    try:
        from src.lib.db import pool

        with pool.connection() as conn:
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
    """
    Performs optimized Hybrid Search (BM25 + Vector) with Cross-Encoding re-ranking.

    Args:
        query (str): The natural language query.
    """
    log_tool_call("semantic_search_tool", query)
    state = _init_search()
    if not state["ready"]:
        return "Error: Search infrastructure is unavailable."

    collection = state["collection"]
    documents = state["documents"]
    metadatas = state["metadatas"]
    bm25 = state["bm25"]

    try:
        expanded_queries = _get_query_expander().invoke({"question": query})
    except Exception as exc:
        logger.warning("Query expansion failed, using original query: %s", exc)
        expanded_queries = [query]

    try:
        query_embeddings = _get_embedding_model().embed_documents(expanded_queries)
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return "Error: could not generate query embeddings."

    try:
        search_results = collection.query(
            query_embeddings=query_embeddings, n_results=15
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return "Error: vector search failed."

    candidate_map = {}

    for i, q in enumerate(expanded_queries):
        q_tokens = q.lower().split()
        bm25_scores = bm25.get_scores(q_tokens)
        top_bm_indices = np.argsort(bm25_scores)[-20:]

        for idx in top_bm_indices:
            score = bm25_scores[idx]
            if score <= 0:
                continue
            doc = documents[idx]
            meta = metadatas[idx] or {}
            eid = meta.get("email_id")
            candidate_map[doc] = {
                "email_id": eid,
                "score": candidate_map.get(doc, {}).get("score", 0) + score,
            }

        v_docs = search_results["documents"][i]
        v_metas = search_results["metadatas"][i]
        v_dists = search_results["distances"][i]

        for v_doc, v_meta, v_dist in zip(v_docs, v_metas, v_dists):
            sim_score = 1.0 / (1.0 + v_dist)
            eid = v_meta.get("email_id") if v_meta else None
            candidate_map[v_doc] = {
                "email_id": eid,
                "score": candidate_map.get(v_doc, {}).get("score", 0)
                + (sim_score * 10),
            }

    if not candidate_map:
        return "No relevant documents found."

    top_candidates = sorted(
        candidate_map.items(), key=lambda x: x[1]["score"], reverse=True
    )[:20]

    pairs = [[query, text] for text, _ in top_candidates]
    cross_scores = _get_cross_encoder().predict(pairs)

    final_ranked = sorted(
        zip(cross_scores, top_candidates), key=lambda x: x[0], reverse=True
    )

    ranked_top = final_ranked[:10]
    sources = _fetch_email_sources(
        [info["email_id"] for _, (_, info) in ranked_top]
    )

    output = []
    for rel_score, (text, info) in ranked_top:
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