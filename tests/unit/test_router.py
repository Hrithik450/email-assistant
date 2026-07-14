"""Unit tests for src/lib/router.py — no external dependencies."""

import pytest
from src.lib.router import classify_complexity, get_model_for_query, MODEL_TIERS


class TestClassifyComplexity:
    # Simple tier
    def test_greeting_hello(self):
        assert classify_complexity("Hello!") == "simple"

    def test_greeting_hi(self):
        assert classify_complexity("hi") == "simple"

    def test_thanks(self):
        assert classify_complexity("Thanks") == "simple"

    # Standard tier
    def test_basic_email_search(self):
        assert classify_complexity("Show me emails from alice@example.com") == "standard"

    def test_date_filter(self):
        result = classify_complexity("Find emails between January and March 2024")
        assert result in ("standard", "complex")

    def test_single_thread_summary(self):
        result = classify_complexity("Summarize the thread about project alpha")
        assert result == "standard"

    # Complex tier
    def test_summarize_all(self):
        assert classify_complexity("Summarize all emails from last month") == "complex"

    def test_compare(self):
        assert classify_complexity("Compare emails from Alice and Bob this quarter") == "complex"

    def test_trend(self):
        assert classify_complexity("Show me the trend in emails over time") == "complex"

    def test_analyze(self):
        assert classify_complexity("Analyze the communication patterns in my inbox") == "complex"

    def test_very_long_query(self):
        long_q = " ".join(["word"] * 55)
        assert classify_complexity(long_q) == "complex"


class TestGetModelForQuery:
    def test_returns_known_model(self):
        model = get_model_for_query("hello")
        assert model in MODEL_TIERS.values()

    def test_simple_gets_lite_model(self):
        assert get_model_for_query("hi") == MODEL_TIERS["simple"]

    def test_complex_gets_pro_model(self):
        assert get_model_for_query("Analyze all email trends") == MODEL_TIERS["complex"]

    def test_standard_gets_flash_model(self):
        assert get_model_for_query("Show me emails from alice") == MODEL_TIERS["standard"]
