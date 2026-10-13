import re

_COMPLEX_KEYWORDS = frozenset([
    "summarize all", "summarise all", "compare", "trend", "analyze", "analyse", 
    "pattern", "across all", "over time", "aggregat", "how many total", "statistics", 
    "breakdown", "group by", "correlation", "insight", "report", "comprehensive", 
    "deep dive", "explain why", "what caused", "root cause", "impact", "forecast"
])

_SIMPLE_KEYWORDS = frozenset([
    "hello", "hi", "hey", "good morning", "good evening", "good afternoon", 
    "thanks", "thank you", "bye", "goodbye", "what is your name", "who are you", 
    "help", "what can you do"
])

_COMPLEX_PATTERNS = [
    re.compile(r"\b(summarize|summarise)\b.{0,60}\b(all|every|entire|whole)\b", re.I),
    re.compile(r"\b(compare|contrast)\b.{0,80}\band\b", re.I),
    re.compile(r"\bhow many\b.{0,40}\b(total|overall|across)\b", re.I),
    re.compile(r"\bwhat (are|were) the (main|key|top|most)\b", re.I),
    re.compile(r"\b(find|show|list).{0,30}\b(pattern|trend|insight)\b", re.I),
]

MODEL_TIERS: dict[str, str] = {
    "simple": "gemini-3.5-flash",
    "standard": "gemini-3.5-flash",
    "complex": "gemini-3.5-flash",
}

def classify_complexity(query: str) -> str:
    q = query.lower().strip()
    if len(q.split()) <= 6:
        for kw in _SIMPLE_KEYWORDS:
            if kw in q:
                return "simple"
    for kw in _COMPLEX_KEYWORDS:
        if kw in q:
            return "complex"
    for pattern in _COMPLEX_PATTERNS:
        if pattern.search(q):
            return "complex"
    if len(q.split()) > 50:
        return "complex"
    return "standard"

def get_model_for_query(query: str) -> str:
    tier = classify_complexity(query)
    return MODEL_TIERS[tier]

def get_tier_and_model(query: str) -> tuple[str, str]:
    tier = classify_complexity(query)
    return tier, MODEL_TIERS[tier]

def get_model_for_tier(tier: str) -> str:
    return MODEL_TIERS.get(tier, MODEL_TIERS["standard"])
