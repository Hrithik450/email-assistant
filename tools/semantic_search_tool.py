from lib.pipeline import chroma_collection
from langchain.tools import tool
from langchain_openai import (
    OpenAIEmbeddings,
)
from lib.utils import EMBEDDING_MODEL_NAME
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi
import numpy as np
import os

GEMINI_API_KEY = os.environ["GOOGLE_API_KEY"]

embedding_model = OpenAIEmbeddings(
    model=EMBEDDING_MODEL_NAME, api_key=os.getenv("OPENAI_API_KEY")
)

# BM25 (An superfast algo which focus more on imp key words to retrieve relavant docs) - will need documents loaded once
if chroma_collection is not None:
    all_chroma = chroma_collection.get(include=["documents", "metadatas"])
    documents = all_chroma["documents"]
    metadatas = all_chroma["metadatas"]

    tokenized_docs = [doc.lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized_docs)

    # Mapping: doc text -> index
    doc_to_index = {doc: i for i, doc in enumerate(documents)}

    index_to_doc = {i: doc for doc, i in doc_to_index.items()}

    doc_to_meta = {
        doc: (meta if meta is not None else {})
        for doc, meta in zip(documents, metadatas or [{}] * len(documents))
    }
else:
    documents = []
    tokenized_docs = []
    bm25 = None

# Cross-encoder (to compare the lists & re-rank based on the semantic meaning)
cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# Query expansion pipeline
template = """You are an AI language model assistant. Your task is to generate 3 
different versions of the given user question to retrieve relevant documents from a vector 
database. By generating multiple perspectives on the user question, your goal is to help
the user overcome some of the limitations of the distance-based similarity search. 
Provide these alternative questions separated by newlines. Original question: {question}"""
prompt_perspectives = ChatPromptTemplate.from_template(template)

generate_queries = (
    prompt_perspectives
    | ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0,
        max_retries=2,
        google_api_key=GEMINI_API_KEY,
    )
    | StrOutputParser()
    | (lambda x: x.split("\n"))
)


@tool("semantic_search_tool", parse_docstring=True)
def semantic_search_tool(query: str) -> str:
    """
    Performs optimized Hybrid Search (BM25 + Vector) with Cross-Encoding re-ranking.

    Args:
        query (str): The natural language query.
    """
    print(f"semantic_search_tool is being called with {query}")

    if chroma_collection is None or bm25 is None:
        return "Error: Search infrastructure is unavailable."

    expanded_queries = generate_queries.invoke({"question": query})

    # 2. Batch Embedding (Massive Latency Saver)
    # One network call instead of len(all_queries) calls
    query_embeddings = embedding_model.embed_documents(expanded_queries)

    # 3. Vector Retrieval (Batch)
    search_results = chroma_collection.query(
        query_embeddings=query_embeddings, n_results=15
    )

    # 4. Hybrid Scoring & Deduplication
    candidate_map = {}  # {doc_text: {"email_id": id, "score": score}}

    for i, q in enumerate(expanded_queries):
        # BM25 - Local calculation is fast
        q_tokens = q.lower().split()
        bm25_scores = bm25.get_scores(q_tokens)
        top_bm_indices = np.argsort(bm25_scores)[-20:]  # Get top 20 indices

        # Process BM25 hits
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

        # Process Vector hits
        v_docs = search_results["documents"][i]
        v_metas = search_results["metadatas"][i]
        v_dists = search_results["distances"][i]

        for v_doc, v_meta, v_dist in zip(v_docs, v_metas, v_dists):
            # Convert distance to similarity (Assume cosine distance 0-2)
            sim_score = 1.0 / (1.0 + v_dist)
            eid = v_meta.get("email_id") if v_meta else None
            candidate_map[v_doc] = {
                "email_id": eid,
                "score": candidate_map.get(v_doc, {}).get("score", 0)
                + (sim_score * 10),
            }

    if not candidate_map:
        return "No relevant documents found."

    # Sort candidates and take top 20 for Cross-Encoding (Expensive part)
    top_candidates = sorted(
        candidate_map.items(), key=lambda x: x[1]["score"], reverse=True
    )[:20]

    pairs = [[query, text] for text, _ in top_candidates]
    cross_scores = cross_encoder.predict(pairs)

    # Pair scores with candidates and sort
    final_ranked = sorted(
        zip(cross_scores, top_candidates), key=lambda x: x[0], reverse=True
    )

    # 6. Format Output
    output = []
    for rel_score, (text, info) in final_ranked[:10]:  # Top 10 results
        prefix = f"[id: {info['email_id']}]\n" if info["email_id"] else ""
        output.append(f"{prefix}{text}")

    return "\n\n---\n\n".join(output)
