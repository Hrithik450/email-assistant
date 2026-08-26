"""Gemini embeddings — the single source of truth for model + vector size.

Both the offline index builder (`scripts/build_vector_index.py`) and the online
search tool (`src/tools/semantic_search_tool.py`) import from here, so the
embedding model and dimensionality can never drift apart.
"""

import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.lib.utils import EMBEDDING_DIM, EMBEDDING_MODEL_NAME
from src.lib.gemini_pool import get_gemini_key


def get_embeddings(task_type: str) -> GoogleGenerativeAIEmbeddings:
    """Return a Gemini embeddings client configured for a retrieval task.

    Args:
        task_type: ``"RETRIEVAL_DOCUMENT"`` when embedding documents for indexing,
            ``"RETRIEVAL_QUERY"`` when embedding a search query. Matching the task
            type on both sides measurably improves retrieval quality.
    """
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIM,
        google_api_key=get_gemini_key(),
    )
