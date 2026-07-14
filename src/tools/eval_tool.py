"""
LangChain tool that lets the agent evaluate its own RAG response quality on demand.

The agent can call this after answering a complex question to self-assess and report
confidence. The result is returned as a human-readable score summary — the agent
includes it in its final response when the user asks for quality introspection.

Token cost: one Gemini call (flash-lite) per invocation — cheap and fast.
"""

from langchain.tools import tool
from src.lib.evaluator import RAGEvaluator
from src.lib.logger import get_logger

logger = get_logger(__name__)

_evaluator = RAGEvaluator()


@tool("rag_eval_tool", parse_docstring=True)
def rag_eval_tool(query: str, retrieved_context: str, generated_answer: str) -> str:
    """
    Evaluate the quality of a RAG retrieval-and-generation cycle.

    Call this when the user explicitly asks about response quality, confidence,
    or accuracy, OR after answering a complex analytical question where self-assessment
    adds value.  Do NOT call it for every response — only when meaningful.

    Args:
        query: The original user question, verbatim.
        retrieved_context: Raw output from the search/filter tools (paste verbatim).
        generated_answer: The final answer you produced for the user.
    """
    try:
        metrics = _evaluator.evaluate_rag(
            query=query,
            context=retrieved_context,
            answer=generated_answer,
        )
        lines = [
            "**RAG Quality Assessment**",
            f"- Context relevance : {metrics.context_relevance:.1f}/5",
            f"- Faithfulness      : {metrics.faithfulness:.1f}/5",
            f"- Answer relevance  : {metrics.answer_relevance:.1f}/5",
            f"- Completeness      : {metrics.completeness:.1f}/5",
            f"- **Overall         : {metrics.overall:.1f}/5**",
            f"- Reasoning: {metrics.reasoning}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("rag_eval_tool error: %s", exc)
        return "Evaluation error: the quality assessment could not be completed."
