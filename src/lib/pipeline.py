import os
import sys

import chromadb
import polars as pl
from dotenv import load_dotenv
from src.lib.utils import CHROMA_COLLECTION_NAME, EMAIL_JSON_PATH

IS_STREAMLIT_ENVIRONMENT = "streamlit" in sys.modules

if IS_STREAMLIT_ENVIRONMENT:
    import streamlit as st

load_dotenv(override=True)

_df: pl.DataFrame | None = None
_chroma_collection = None
_loaded = False


def _load_resources_base():
    if IS_STREAMLIT_ENVIRONMENT:
        import gdown

        output_path_mails = "raw_mails.jsonl"
        if not os.path.exists(output_path_mails):
            with st.spinner(
                "Downloading metadata from Google Drive (first-time setup)..."
            ):
                gdown.download(
                    id=st.secrets["EMAIL_JSONL_GDRIVE_ID"],
                    output=output_path_mails,
                    quiet=False,
                )
        data_path = output_path_mails
    else:
        data_path = EMAIL_JSON_PATH
        if not os.path.exists(data_path):
            raise FileNotFoundError(
                f"Local data file not found at '{data_path}'. Please ensure it exists before running."
            )

    loaded_df = pl.read_ndjson(data_path)

    try:
        if IS_STREAMLIT_ENVIRONMENT:
            client = chromadb.CloudClient(
                api_key=st.secrets["CHROMA_API_KEY"],
                tenant=st.secrets["CHROMA_TENANT"],
                database=st.secrets["CHROMA_DATABASE"],
            )
        else:
            client = chromadb.CloudClient(
                api_key=os.environ.get("CHROMA_API_KEY", ""),
                tenant=os.environ.get("CHROMA_TENANT", ""),
                database=os.environ.get("CHROMA_DATABASE", ""),
            )
        collection = client.get_collection(name=CHROMA_COLLECTION_NAME)
    except Exception as e:
        from src.lib.logger import get_logger
        get_logger(__name__).warning("Could not connect to ChromaDB: %s", e)
        collection = None

    return loaded_df, collection


def _ensure_loaded():
    global _df, _chroma_collection, _loaded
    if _loaded:
        return

    if IS_STREAMLIT_ENVIRONMENT:
        @st.cache_resource
        def _cached_load():
            return _load_resources_base()

        _df, _chroma_collection = _cached_load()
    else:
        _df, _chroma_collection = _load_resources_base()

    _loaded = True


def __getattr__(name: str):
    if name == "df":
        _ensure_loaded()
        return _df
    if name == "chroma_collection":
        _ensure_loaded()
        return _chroma_collection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
