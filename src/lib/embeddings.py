from webbrowser import get

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.lib.utils import EMBEDDING_DIM, EMBEDDING_MODEL_NAME
from src.lib.gemini_pool import get_gemini_key

def get_embeddings(task_type: str, key: str = None) -> GoogleGenerativeAIEmbeddings:
    api_key = key or get_gemini_key()
    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIM,
        google_api_key=api_key,
    )
