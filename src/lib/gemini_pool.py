import os
import itertools
from threading import Lock


class _GeminiKeyPool:
    """A thread-safe round-robin pool for Gemini API keys."""

    def __init__(self):
        self._keys: list[str] = []
        self._iterator = None
        self._lock = Lock()
        self._initialized = False

    def _init_keys(self):
        if main_key := os.environ.get("GOOGLE_API_KEY"):
            self._keys.append(main_key)

        # 2. Add fallback keys in sorted order
        fallback_keys = sorted(
            (k, v)
            for k, v in os.environ.items()
            if k.startswith("GEMINI_API_KEY_") and v
        )

        for _, v in fallback_keys:
            if v not in self._keys:
                self._keys.append(v)

        if not self._keys:
            raise ValueError(
                "No Gemini API keys found in environment. Ensure GOOGLE_API_KEY is set."
            )

        self._iterator = itertools.cycle(self._keys)
        self._initialized = True

    def get_key(self) -> str:
        with self._lock:
            if not self._initialized:
                self._init_keys()
            return next(self._iterator)


_pool = _GeminiKeyPool()


def get_gemini_key() -> str:
    """
    Return the next Gemini API key from the pool (round-robin).
    Distributes load across GOOGLE_API_KEY and GEMINI_API_KEY_*.
    """
    return _pool.get_key()
