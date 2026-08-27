import re

_COMPLEX_KEYWORDS = frozenset(
    [
        "summarize all",
        "summarise all",
        "compare",
        "trend",
        "analyze",
        "analyse",
        "pattern",
        "across all",
        "over time",
        "aggregat",
        "how many total",
        "statistics",
        "breakdown",
        "group by",
        "correlation",
        "insight",
        "report",
        "comprehensive",
        "deep dive",
        "explain why",
        "what caused",
        "root cause",
        "impact",
        "forecast",
    ]
)

_SIMPLE_KEYWORDS = frozenset(
    [
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
        "good afternoon",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "what is your name",
        "who are you",
        "help",
        "what can you do",
    ]
)

_COMPLEX_PATTERNS = [
    re.compile(r"\b(summarize|summarise)\b.{0,60}\b(all|every|entire|whole)\b", re.I),
    re.compile(r"\b(compare|contrast)\b.{0,80}\band\b", re.I),
    re.compile(r"\bhow many\b.{0,40}\b(total|overall|across)\b", re.I),
    re.compile(r"\bwhat (are|were) the (main|key|top|most)\b", re.I),
    re.compile(r"\b(find|show|list).{0,30}\b(pattern|trend|insight)\b", re.I),
]


MODEL_TIERS: dict[str, str] = {
    "simple": "gpt-4o-mini",
    "standard": "gpt-4o",
    "complex": "o1-preview",
}


def classify_complexity(query: str) -> str:
    """
    Return 'simple', 'standard', or 'complex' for the given user query.
    Uses keyword matching and regex patterns — no LLM call.
    """
    q = query.lower().strip()

    # Exact / phrase match for simple greetings / short social messages
    if len(q.split()) <= 6:
        for kw in _SIMPLE_KEYWORDS:
            if kw in q:
                return "simple"

    # Complex: keyword or pattern match
    for kw in _COMPLEX_KEYWORDS:
        if kw in q:
            return "complex"

    for pattern in _COMPLEX_PATTERNS:
        if pattern.search(q):
            return "complex"

    # Complex: very long queries are likely multi-step requests
    if len(q.split()) > 50:
        return "complex"

    return "standard"


def get_model_for_query(query: str) -> str:
    """Return the Gemini model name appropriate for this query."""
    tier = classify_complexity(query)
    return MODEL_TIERS[tier]


def get_tier_and_model(query: str) -> tuple[str, str]:
    """Return (tier, model_name) for a query.

    Prefer this over reverse-mapping a model name back to a tier: several tiers
    may share the same model, so that reverse lookup is ambiguous.
    """
    tier = classify_complexity(query)
    return tier, MODEL_TIERS[tier]


def get_model_for_tier(tier: str) -> str:
    """Return model name for an explicit tier string."""
    return MODEL_TIERS.get(tier, MODEL_TIERS["standard"])
