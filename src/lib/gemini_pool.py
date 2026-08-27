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
