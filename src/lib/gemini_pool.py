import os
import time
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Maintain cooldowns for keys
_cooldowns = {}

def get_gemini_key(service: str = "embedding") -> str:
    """Returns a Gemini API key. Could be expanded later to support a pool of Gemini keys."""
    return os.environ.get("GOOGLE_API_KEY", "")

def mark_key_exhausted(key: str, cooldown_secs: int = 60):
    _cooldowns[key] = time.time() + cooldown_secs

def embed_with_pooling(query: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """
    Handles Gemini embedding generation with automatic pooling and key switching on quota errors.
    """
    from src.lib.embeddings import get_embeddings
    
    last_err = None
    for attempt in range(2):
        key = get_gemini_key("embedding")
        
        # In a real pool, get_gemini_key would check _cooldowns. 
        # For now, if the only key is exhausted, we still wait.
        now = time.time()
        if _cooldowns.get(key, 0) > now:
            wait_time = _cooldowns[key] - now
            print(f"Gemini key on cooldown for {wait_time:.1f}s...")
            time.sleep(min(wait_time, 2.0)) # sleep a bit or fail fast
            
        try:
            embedder = get_embeddings(task_type, key=key)
            return embedder.embed_query(query)
        except Exception as e:
            err_str = str(type(e).__name__).lower() + " " + str(e).lower()
            if any(
                x in err_str for x in [
                    "429", "503", "401", "403", 
                    "resource_exhausted", "unavailable", 
                    "unauthenticated", "permission_denied", "not_found", "valueerror"
                ]
            ):
                print(f"Gemini key exhausted (attempt {attempt+1}), cooling down...")
                mark_key_exhausted(key, cooldown_secs=60)
                last_err = e
                continue
            raise e
    raise RuntimeError(f"All Gemini keys exhausted. Last error: {last_err}")
