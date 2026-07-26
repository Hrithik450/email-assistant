"""
Evaluation framework for the RE-assistant RAG system and agent.

Design:
- Single LLM call per evaluation (all metrics batched into one prompt) → minimal token use.
- LLM-as-judge scores each dimension 1-5 and returns structured JSON.
- All metrics are data-classes so callers can aggregate, compare, or serialize them.
- The evaluator is independently instantiable (no global state) — safe for testing.

Evaluation dimensions
─────────────────────
RAGMetrics
  context_relevance  - Are the retrieved chunks relevant to the query?
  faithfulness       - Does the answer stay grounded in the retrieved context?
  answer_relevance   - Does the answer directly address the original query?
  completeness       - Does the answer cover all aspects the query asked for?

AgentMetrics
  response_quality   - Is the response well-formatted and professional?
  factual_grounding  - Are stated facts traceable to retrieved data (not hallucinated)?
  tool_appropriateness - Did the agent select the right tools for the query?
  conciseness        - Is the response appropriately concise (not bloated)?
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv(override=True)

_EVAL_MODEL = "gemini-2.5-flash-lite"  # cheapest / fastest — good enough for scoring

_RAG_PROMPT = """\
You are a strict evaluation judge for a Retrieval-Augmented Generation (RAG) system.

Score each dimension from 1 (very poor) to 5 (excellent) based ONLY on the inputs below.
Be critical: award 5 only when the dimension is fully satisfied.

Query:
{query}

Retrieved Context (raw tool output):
{context}

Generated Answer:
{answer}

Score these four dimensions:
1. context_relevance  - How relevant are the retrieved chunks to answering the query?
2. faithfulness       - Does the answer use ONLY information present in the retrieved context (no hallucination)?
3. answer_relevance   - Does the answer directly and completely address the query?
4. completeness       - Does the answer cover all aspects the query asked for?

Reply with ONLY valid JSON (no markdown fences), example:
{{"context_relevance": 4, "faithfulness": 5, "answer_relevance": 3, "completeness": 4, "reasoning": "one concise sentence"}}
"""

_AGENT_PROMPT = """\
You are a strict evaluation judge for an AI assistant.

Score each dimension from 1 (very poor) to 5 (excellent).

User Query:
{query}

Tool Calls Made (list of tool names, or "none"):
{tool_calls}

Agent Answer:
{answer}

{expected_block}

Score these four dimensions:
1. response_quality    - Is the response well-formatted, professional, and readable?
2. factual_grounding   - Are all stated facts grounded in retrieved data (not invented)?
3. tool_appropriateness - Did the agent use appropriate tools (right tool, right arguments)?
4. conciseness         - Is the answer appropriately concise without omitting key information?

Reply with ONLY valid JSON (no markdown fences), example:
{{"response_quality": 4, "factual_grounding": 5, "tool_appropriateness": 3, "conciseness": 4, "reasoning": "one concise sentence"}}
"""


@dataclass
class RAGMetrics:
    context_relevance: float
    faithfulness: float
    answer_relevance: float
    completeness: float
    overall: float
    reasoning: str

    def to_dict(self) -> dict:
        return asdict(self)

    def passed(self, threshold: float = 3.0) -> bool:
        return self.overall >= threshold


@dataclass
class AgentMetrics:
    response_quality: float
    factual_grounding: float
    tool_appropriateness: float
    conciseness: float
    overall: float
    reasoning: str

    def to_dict(self) -> dict:
        return asdict(self)

    def passed(self, threshold: float = 3.0) -> bool:
        return self.overall >= threshold


@dataclass
class EvalReport:
    """Aggregated result from running a test suite."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_overall: float = 0.0
    avg_context_relevance: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    avg_completeness: float = 0.0
    results: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Evaluation Report  ({self.passed}/{self.total} passed, threshold ≥ 3.0)",
            f"  Overall avg        : {self.avg_overall:.2f}",
            f"  Context relevance  : {self.avg_context_relevance:.2f}",
            f"  Faithfulness       : {self.avg_faithfulness:.2f}",
            f"  Answer relevance   : {self.avg_answer_relevance:.2f}",
            f"  Completeness       : {self.avg_completeness:.2f}",
        ]
        return "\n".join(lines)


def _parse_json_safely(raw: str) -> dict:
    """Strip markdown fences then parse JSON; raise ValueError on failure."""
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    return json.loads(cleaned)


def _weighted_avg(scores: dict, weights: dict) -> float:
    total_w = sum(weights.values())
    return sum(scores[k] * weights[k] for k in weights) / total_w


class RAGEvaluator:
    """
    Evaluate RAG retrieval and generation quality using an LLM judge.

    Usage::

        ev = RAGEvaluator()
        metrics = ev.evaluate_rag(
            query="Who sent the email about project alpha?",
            context="<raw output from semantic_search_tool>",
            answer="<final agent answer>",
        )
        print(metrics.overall, metrics.reasoning)
    """

    _RAG_WEIGHTS = {
        "context_relevance": 0.30,
        "faithfulness": 0.30,
        "answer_relevance": 0.25,
        "completeness": 0.15,
    }

    _AGENT_WEIGHTS = {
        "response_quality": 0.25,
        "factual_grounding": 0.35,
        "tool_appropriateness": 0.25,
        "conciseness": 0.15,
    }

    def __init__(self, model: str = _EVAL_MODEL):
        self._model_name = model
        self._llm = None  # lazy-init so tests can instantiate without API keys

    def _get_llm(self):
        if self._llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._llm = ChatGoogleGenerativeAI(
                model=self._model_name,
                temperature=0,
                max_retries=2,
                google_api_key=os.environ["GOOGLE_API_KEY"],
            )
        return self._llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_rag(
        self,
        query: str,
        context: str,
        answer: str,
    ) -> RAGMetrics:
        """Score a single RAG query-context-answer triple."""
        prompt = _RAG_PROMPT.format(
            query=query.strip(),
            context=context.strip()[:4000],  # guard against huge contexts
            answer=answer.strip(),
        )
        raw = self._get_llm().invoke(prompt).content
        data = _parse_json_safely(raw)

        scores = {k: float(data.get(k, 3)) for k in self._RAG_WEIGHTS}
        overall = _weighted_avg(scores, self._RAG_WEIGHTS)

        return RAGMetrics(
            **scores,
            overall=round(overall, 2),
            reasoning=data.get("reasoning", ""),
        )

    def evaluate_agent(
        self,
        query: str,
        answer: str,
        tool_calls: list[str] | None = None,
        expected_answer: str | None = None,
    ) -> AgentMetrics:
        """Score a single agent query-answer pair."""
        tool_str = ", ".join(tool_calls) if tool_calls else "none"
        expected_block = (
            f"Expected Answer (ground truth):\n{expected_answer}"
            if expected_answer
            else "(no ground truth provided — judge on reasonableness)"
        )
        prompt = _AGENT_PROMPT.format(
            query=query.strip(),
            tool_calls=tool_str,
            answer=answer.strip(),
            expected_block=expected_block,
        )
        raw = self._get_llm().invoke(prompt).content
        data = _parse_json_safely(raw)

        scores = {k: float(data.get(k, 3)) for k in self._AGENT_WEIGHTS}
        overall = _weighted_avg(scores, self._AGENT_WEIGHTS)

        return AgentMetrics(
            **scores,
            overall=round(overall, 2),
            reasoning=data.get("reasoning", ""),
        )

    def run_rag_suite(
        self,
        test_cases: list[dict],
        threshold: float = 3.0,
        delay_between: float = 0.3,
    ) -> EvalReport:
        """
        Run evaluate_rag() over a list of test-case dicts.

        Each dict must have: query, context, answer.
        Optionally: label (human-readable name for the test).
        """
        report = EvalReport(total=len(test_cases))
        all_metrics: list[RAGMetrics] = []

        for i, tc in enumerate(test_cases):
            label = tc.get("label", f"case_{i}")
            try:
                m = self.evaluate_rag(tc["query"], tc["context"], tc["answer"])
                all_metrics.append(m)
                ok = m.passed(threshold)
                report.passed += int(ok)
                report.failed += int(not ok)
                report.results.append(
                    {
                        "label": label,
                        "passed": ok,
                        "metrics": m.to_dict(),
                    }
                )
            except Exception as exc:
                report.failed += 1
                report.results.append(
                    {"label": label, "passed": False, "error": str(exc)}
                )
            if delay_between and i < len(test_cases) - 1:
                time.sleep(delay_between)

        if all_metrics:
            n = len(all_metrics)
            report.avg_overall = round(sum(m.overall for m in all_metrics) / n, 2)
            report.avg_context_relevance = round(
                sum(m.context_relevance for m in all_metrics) / n, 2
            )
            report.avg_faithfulness = round(
                sum(m.faithfulness for m in all_metrics) / n, 2
            )
            report.avg_answer_relevance = round(
                sum(m.answer_relevance for m in all_metrics) / n, 2
            )
            report.avg_completeness = round(
                sum(m.completeness for m in all_metrics) / n, 2
            )

        return report
