import os
import time
from langchain_openai import ChatOpenAI

OPENAI_NATIVE_KEY = os.environ.get("OPENAI_API_KEY", "")
AICREDITS_KEY = os.environ.get("AICREDITS_KEY", "")

_cooldowns = {}


def get_llm(model_name: str, tools=None):
    """Returns a ChatOpenAI instance, prioritizing OpenAI key, falling back to AICredits."""
    now = time.time()

    if OPENAI_NATIVE_KEY and _cooldowns.get(OPENAI_NATIVE_KEY, 0) < now:
        llm = ChatOpenAI(
            model=model_name, temperature=0.4, max_retries=0, api_key=OPENAI_NATIVE_KEY
        )
        if tools:
            return llm.bind_tools(tools)
        return llm

    if _cooldowns.get(AICREDITS_KEY, 0) < now:
        llm = ChatOpenAI(
            base_url="https://api.aicredits.in/v1",
            model=model_name,
            temperature=0.4,
            max_retries=0,
            api_key=AICREDITS_KEY,
        )
        if tools:
            return llm.bind_tools(tools)
        return llm

    raise RuntimeError("All LLM API keys are on cooldown or exhausted.")


def mark_key_exhausted(is_native: bool, cooldown_secs: int = 60):
    key = OPENAI_NATIVE_KEY if is_native else AICREDITS_KEY
    _cooldowns[key] = time.time() + cooldown_secs


def invoke_with_pooling(model_name: str, messages: list, tools=None):
    """
    Handles LLM invocation with automatic pooling and key switching on quota errors.
    """
    last_err = None
    for attempt in range(2):
        try:
            llm = get_llm(model_name, tools)
            return llm.invoke(messages)
        except Exception as e:
            err_str = str(type(e).__name__).lower() + " " + str(e).lower()
            if any(
                x in err_str
                for x in [
                    "429",
                    "503",
                    "403",
                    "ratelimiterror",
                    "insufficient_quota",
                    "resourceexhaustederror",
                    "permissiondeniederror",
                ]
            ):
                print(
                    f"LLM key exhausted (attempt {attempt+1}), switching to backup..."
                )
                is_native = "aicredits" not in err_str
                mark_key_exhausted(is_native=is_native, cooldown_secs=300)
                last_err = e
                continue
            raise e
    raise RuntimeError(f"All LLM keys exhausted. Last error: {last_err}")


def get_openai_embeddings(is_native: bool = True):
    """Returns an OpenAIEmbeddings instance, using native or backup key."""
    from langchain_openai import OpenAIEmbeddings
    from src.lib.utils import EMBEDDING_DIM
    
    if is_native:
        return OpenAIEmbeddings(
            model="text-embedding-3-large", 
            dimensions=EMBEDDING_DIM,
            api_key=OPENAI_NATIVE_KEY
        )
    else:
        return OpenAIEmbeddings(
            base_url="https://api.aicredits.in/v1",
            model="text-embedding-3-large",
            dimensions=EMBEDDING_DIM,
            api_key=AICREDITS_KEY
        )

def openai_embed_with_pooling(query: str) -> list[float]:
    """
    Handles OpenAI embedding generation with automatic pooling and key switching on quota errors.
    """
    last_err = None
    now = time.time()
    
    # Try Priority 1 (Native)
    if OPENAI_NATIVE_KEY and _cooldowns.get(OPENAI_NATIVE_KEY, 0) < now:
        try:
            return get_openai_embeddings(is_native=True).embed_query(query)
        except Exception as e:
            err_str = str(type(e).__name__).lower() + " " + str(e).lower()
            if any(x in err_str for x in ["429", "503", "403", "ratelimiterror", "insufficient_quota"]):
                print("Native OpenAI key exhausted for embeddings, switching to backup...")
                mark_key_exhausted(is_native=True, cooldown_secs=300)
                last_err = e
            else:
                raise e

    # Try Priority 2 (AICredits)
    if _cooldowns.get(AICREDITS_KEY, 0) < time.time():
        try:
            return get_openai_embeddings(is_native=False).embed_query(query)
        except Exception as e:
            err_str = str(type(e).__name__).lower() + " " + str(e).lower()
            if any(x in err_str for x in ["429", "503", "403", "ratelimiterror", "insufficient_quota"]):
                print("AICredits key exhausted for embeddings, cooling down...")
                mark_key_exhausted(is_native=False, cooldown_secs=300)
                last_err = e
            else:
                raise e

    raise RuntimeError(f"All OpenAI embedding keys exhausted. Last error: {last_err}")
