import os
import time
from langchain_openai import ChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.lib.utils import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

# The OpenAI key from .env (Priority 1)
OPENAI_NATIVE_KEY = os.environ.get("OPENAI_API_KEY", "")
# The AI Credits key (Priority 2)
AICREDITS_KEY = "sk-live-7e0f40f473d4f819496fcdbcecb579fbdc660317440d9c1d01f9d52a01cded28"

# Maintain cooldowns for keys
_cooldowns = {}

def get_llm(model_name: str, tools=None):
    """Returns a ChatOpenAI instance, prioritizing OpenAI key, falling back to AICredits."""
    now = time.time()
    
    # Priority 1: Native OpenAI
    if OPENAI_NATIVE_KEY and _cooldowns.get(OPENAI_NATIVE_KEY, 0) < now:
        llm = ChatOpenAI(
            model=model_name,
            temperature=0.4,
            max_retries=0,
            api_key=OPENAI_NATIVE_KEY
        )
        if tools:
            return llm.bind_tools(tools)
        return llm

    # Priority 2: AICredits
    if _cooldowns.get(AICREDITS_KEY, 0) < now:
        llm = ChatOpenAI(
            base_url="https://api.aicredits.in/v1",
            model=model_name,
            temperature=0.4,
            max_retries=0,
            api_key=AICREDITS_KEY
        )
        if tools:
            return llm.bind_tools(tools)
        return llm
        
    raise RuntimeError("All LLM API keys are on cooldown or exhausted.")

def mark_key_exhausted(is_native: bool, cooldown_secs: int = 60):
    key = OPENAI_NATIVE_KEY if is_native else AICREDITS_KEY
    _cooldowns[key] = time.time() + cooldown_secs

def get_gemini_key(purpose: str) -> str:
    # Just for embeddings backward compatibility in embeddings.py
    return os.environ.get("GOOGLE_API_KEY", "")
