import os
import sys
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.lib.utils import EMBEDDING_DIM, EMBEDDING_MODEL_NAME


def get_gemini_api_key() -> str:
    """Return the Google API key from environment variables or Streamlit secrets."""
    if "streamlit" in sys.modules:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
                return st.secrets["GOOGLE_API_KEY"]
        except Exception:
            pass
    return os.environ.get("GOOGLE_API_KEY", "")


get_gemini_key = get_gemini_api_key


def get_embeddings(task_type: str = "RETRIEVAL_QUERY", key: str | None = None) -> GoogleGenerativeAIEmbeddings:
    api_key = key or get_gemini_api_key()
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIM,
        google_api_key=api_key,
    )


def embed_query(query: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Generate a 3072-dimension query embedding directly using Gemini."""
    embedder = get_embeddings(task_type=task_type)
    return embedder.embed_query(query)
