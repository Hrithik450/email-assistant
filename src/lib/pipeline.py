import os
import sys
import chromadb
from dotenv import load_dotenv

load_dotenv(override=True)

IS_STREAMLIT_ENVIRONMENT = "streamlit" in sys.modules

_chroma_collection = None
_loaded = False


def get_chroma_client():
    api_key = os.environ.get("CHROMA_API_KEY", "")
    tenant = os.environ.get("CHROMA_TENANT", "")
    database = os.environ.get("CHROMA_DATABASE", "")
    
    if IS_STREAMLIT_ENVIRONMENT:
        import streamlit as st
        api_key = st.secrets.get("CHROMA_API_KEY", api_key)
        tenant = st.secrets.get("CHROMA_TENANT", tenant)
        database = st.secrets.get("CHROMA_DATABASE", database)

    return chromadb.CloudClient(
        api_key=api_key,
        tenant=tenant,
        database=database,
    )


def get_chroma_collection(collection_name: str = "organization_data"):
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    try:
        client = get_chroma_client()
        _chroma_collection = client.get_collection(name=collection_name)
    except Exception as e:
        from src.lib.logger import get_logger
        get_logger(__name__).warning("Could not connect to ChromaDB: %s", e)
        _chroma_collection = None

    return _chroma_collection


def __getattr__(name: str):
    if name == "chroma_collection":
        return get_chroma_collection()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
