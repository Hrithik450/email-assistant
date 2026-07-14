"""
Tests for src/lib/evaluator.py and src/tools/eval_tool.py.

Unit tests mock the LLM so no API key is required.
Integration tests (marked live_llm) hit the real Gemini API and require GOOGLE_API_KEY.
"""

from __future__ import annotations

import json
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from tests.eval.eval_cases import RAG_TEST_CASES, AGENT_TEST_CASES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(data: dict):
    """Return a mock LLM response whose .content is a JSON string."""
    mock = MagicMock()
    mock.content = json.dumps(data)
    return mock


# ---------------------------------------------------------------------------
# Unit: RAGMetrics / AgentMetrics dataclass contracts
# ---------------------------------------------------------------------------


class TestMetricsDataclasses:
    def test_rag_metrics_fields(self):
        from src.lib.evaluator import RAGMetrics

        m = RAGMetrics(
            context_relevance=4,
            faithfulness=5,
            answer_relevance=3,
            completeness=4,
            overall=4.05,
            reasoning="looks good",
        )
        assert m.overall == 4.05
        assert m.passed(threshold=3.0) is True
        assert m.passed(threshold=4.1) is False

    def test_agent_metrics_fields(self):
        from src.lib.evaluator import AgentMetrics

        m = AgentMetrics(
            response_quality=4,
            factual_grounding=5,
            tool_appropriateness=4,
            conciseness=3,
            overall=4.1,
            reasoning="solid",
        )
        assert m.passed(threshold=4.0) is True
        assert m.to_dict()["factual_grounding"] == 5

    def test_rag_to_dict_has_all_keys(self):
        from src.lib.evaluator import RAGMetrics

        m = RAGMetrics(
            context_relevance=3,
            faithfulness=3,
            answer_relevance=3,
            completeness=3,
            overall=3.0,
            reasoning="ok",
        )
        d = m.to_dict()
        for key in (
            "context_relevance",
            "faithfulness",
            "answer_relevance",
            "completeness",
            "overall",
            "reasoning",
        ):
            assert key in d


# ---------------------------------------------------------------------------
# Unit: _parse_json_safely
# ---------------------------------------------------------------------------


class TestParseJsonSafely:
    def test_plain_json(self):
        from src.lib.evaluator import _parse_json_safely

        data = _parse_json_safely('{"a": 1, "b": 2}')
        assert data == {"a": 1, "b": 2}

    def test_strips_markdown_fences(self):
        from src.lib.evaluator import _parse_json_safely

        raw = '```json\n{"a": 1}\n```'
        assert _parse_json_safely(raw) == {"a": 1}

    def test_strips_plain_fences(self):
        from src.lib.evaluator import _parse_json_safely

        raw = '```\n{"x": 99}\n```'
        assert _parse_json_safely(raw) == {"x": 99}

    def test_invalid_raises(self):
        from src.lib.evaluator import _parse_json_safely

        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_json_safely("not json at all")


# ---------------------------------------------------------------------------
# Unit: _weighted_avg
# ---------------------------------------------------------------------------


class TestWeightedAvg:
    def test_equal_weights(self):
        from src.lib.evaluator import _weighted_avg

        scores = {"a": 4, "b": 2}
        weights = {"a": 1, "b": 1}
        assert _weighted_avg(scores, weights) == 3.0

    def test_unequal_weights(self):
        from src.lib.evaluator import _weighted_avg

        scores = {"a": 5, "b": 1}
        weights = {"a": 3, "b": 1}
        result = _weighted_avg(scores, weights)
        assert abs(result - 4.0) < 1e-9


# ---------------------------------------------------------------------------
# Unit: RAGEvaluator.evaluate_rag (mocked LLM)
# ---------------------------------------------------------------------------


class TestRAGEvaluatorMocked:
    @pytest.fixture
    def evaluator(self):
        from src.lib.evaluator import RAGEvaluator

        ev = RAGEvaluator()
        ev._llm = MagicMock()
        return ev

    def test_evaluate_rag_returns_metrics(self, evaluator):
        from src.lib.evaluator import RAGMetrics

        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "context_relevance": 4,
                "faithfulness": 5,
                "answer_relevance": 4,
                "completeness": 3,
                "reasoning": "good retrieval",
            }
        )
        m = evaluator.evaluate_rag(
            query="Who sent the email?",
            context="From: alice@example.com",
            answer="Alice sent the email.",
        )
        assert isinstance(m, RAGMetrics)
        assert m.faithfulness == 5.0
        assert 0 < m.overall <= 5.0
        assert "good retrieval" in m.reasoning

    def test_evaluate_rag_clamps_missing_fields_to_3(self, evaluator):
        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "context_relevance": 4,
                # faithfulness and others missing
                "reasoning": "partial",
            }
        )
        m = evaluator.evaluate_rag("q", "ctx", "ans")
        assert m.faithfulness == 3.0
        assert m.answer_relevance == 3.0

    def test_evaluate_agent_returns_metrics(self, evaluator):
        from src.lib.evaluator import AgentMetrics

        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "response_quality": 5,
                "factual_grounding": 4,
                "tool_appropriateness": 5,
                "conciseness": 4,
                "reasoning": "used right tools",
            }
        )
        m = evaluator.evaluate_agent(
            query="Show me emails from Alice",
            answer="Here are the emails from Alice…",
            tool_calls=["email_filtering_tool"],
        )
        assert isinstance(m, AgentMetrics)
        assert m.tool_appropriateness == 5.0

    def test_evaluate_agent_with_expected(self, evaluator):
        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "response_quality": 3,
                "factual_grounding": 4,
                "tool_appropriateness": 3,
                "conciseness": 3,
                "reasoning": "acceptable",
            }
        )
        m = evaluator.evaluate_agent(
            query="Who sent the email?",
            answer="Milin Sharma sent it.",
            expected_answer="Milin Sharma",
        )
        assert m.passed(3.0) is True

    def test_overall_is_weighted_correctly(self, evaluator):
        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "context_relevance": 5,
                "faithfulness": 5,
                "answer_relevance": 5,
                "completeness": 5,
                "reasoning": "perfect",
            }
        )
        m = evaluator.evaluate_rag("q", "ctx", "ans")
        assert abs(m.overall - 5.0) < 0.01


# ---------------------------------------------------------------------------
# Unit: run_rag_suite (mocked LLM)
# ---------------------------------------------------------------------------


class TestRunRagSuite:
    @pytest.fixture
    def evaluator(self):
        from src.lib.evaluator import RAGEvaluator

        ev = RAGEvaluator()
        ev._llm = MagicMock()
        return ev

    def test_suite_counts_correctly(self, evaluator):
        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "context_relevance": 4,
                "faithfulness": 4,
                "answer_relevance": 4,
                "completeness": 4,
                "reasoning": "ok",
            }
        )
        cases = [
            {"query": "q1", "context": "ctx1", "answer": "a1"},
            {"query": "q2", "context": "ctx2", "answer": "a2"},
        ]
        report = evaluator.run_rag_suite(cases, delay_between=0)
        assert report.total == 2
        assert report.passed == 2
        assert report.failed == 0

    def test_suite_failed_case_counted(self, evaluator):
        # Returns scores below threshold for first case, above for second
        responses = [
            _make_llm_response(
                {
                    "context_relevance": 1,
                    "faithfulness": 1,
                    "answer_relevance": 1,
                    "completeness": 1,
                    "reasoning": "bad",
                }
            ),
            _make_llm_response(
                {
                    "context_relevance": 5,
                    "faithfulness": 5,
                    "answer_relevance": 5,
                    "completeness": 5,
                    "reasoning": "good",
                }
            ),
        ]
        evaluator._llm.invoke.side_effect = responses
        cases = [
            {"query": "q1", "context": "c1", "answer": "a1"},
            {"query": "q2", "context": "c2", "answer": "a2"},
        ]
        report = evaluator.run_rag_suite(cases, threshold=3.0, delay_between=0)
        assert report.failed == 1
        assert report.passed == 1

    def test_suite_report_summary_contains_avg(self, evaluator):
        evaluator._llm.invoke.return_value = _make_llm_response(
            {
                "context_relevance": 3,
                "faithfulness": 3,
                "answer_relevance": 3,
                "completeness": 3,
                "reasoning": "meh",
            }
        )
        cases = [{"query": "q", "context": "c", "answer": "a"}]
        report = evaluator.run_rag_suite(cases, delay_between=0)
        summary = report.summary()
        assert "Overall avg" in summary
        assert "Faithfulness" in summary

    def test_suite_eval_cases_are_valid_dicts(self):
        """All eval_cases entries have required keys."""
        for tc in RAG_TEST_CASES:
            assert "query" in tc
            assert "context" in tc
            assert "answer" in tc


# ---------------------------------------------------------------------------
# Unit: eval_tool (mocked evaluator)
# ---------------------------------------------------------------------------


class TestEvalTool:
    def test_returns_score_string(self):
        from src.lib.evaluator import RAGMetrics

        mock_metrics = RAGMetrics(
            context_relevance=4,
            faithfulness=5,
            answer_relevance=4,
            completeness=3,
            overall=4.2,
            reasoning="solid retrieval",
        )

        with patch("src.tools.eval_tool._evaluator") as mock_ev:
            mock_ev.evaluate_rag.return_value = mock_metrics
            from src.tools.eval_tool import rag_eval_tool

            result = rag_eval_tool.invoke(
                {
                    "query": "test query",
                    "retrieved_context": "some context",
                    "generated_answer": "some answer",
                }
            )

        assert "4.2" in result
        assert "Faithfulness" in result
        assert "solid retrieval" in result

    def test_handles_evaluator_exception_gracefully(self):
        with patch("src.tools.eval_tool._evaluator") as mock_ev:
            mock_ev.evaluate_rag.side_effect = RuntimeError("API down")
            from src.tools.eval_tool import rag_eval_tool

            result = rag_eval_tool.invoke(
                {
                    "query": "q",
                    "retrieved_context": "c",
                    "generated_answer": "a",
                }
            )
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Integration: live LLM (requires GOOGLE_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("os").environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set — skipping live LLM eval tests",
)
class TestRAGEvaluatorLive:
    @pytest.fixture(scope="class")
    def evaluator(self):
        from src.lib.evaluator import RAGEvaluator

        return RAGEvaluator()

    def test_high_quality_case_scores_well(self, evaluator):
        tc = RAG_TEST_CASES[0]  # sender_lookup — clear context + correct answer
        m = evaluator.evaluate_rag(tc["query"], tc["context"], tc["answer"])
        assert (
            m.overall >= 3.5
        ), f"Expected ≥3.5, got {m.overall}. Reason: {m.reasoning}"

    def test_no_results_case_scores_faithfully(self, evaluator):
        tc = next(c for c in RAG_TEST_CASES if c["label"] == "no_results_handling")
        m = evaluator.evaluate_rag(tc["query"], tc["context"], tc["answer"])
        assert m.faithfulness >= 3.0, f"Faithfulness too low: {m.faithfulness}"

    def test_hallucination_check_scores_faithfully(self, evaluator):
        tc = next(c for c in RAG_TEST_CASES if c["label"] == "hallucination_check")
        m = evaluator.evaluate_rag(tc["query"], tc["context"], tc["answer"])
        assert (
            m.faithfulness >= 3.5
        ), f"Faithfulness should be high for honest 'not mentioned' answer"

    def test_run_suite_all_cases(self, evaluator):
        report = evaluator.run_rag_suite(RAG_TEST_CASES, delay_between=0.5)
        assert report.total == len(RAG_TEST_CASES)
        assert report.avg_overall > 0
        print("\n" + report.summary())
