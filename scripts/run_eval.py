"""
Standalone evaluation runner.

Usage:
    uv run python scripts/run_eval.py             # run RAG suite + agent suite
    uv run python scripts/run_eval.py --rag       # RAG suite only
    uv run python scripts/run_eval.py --agent     # agent suite only
    uv run python scripts/run_eval.py --threshold 3.5
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(override=True)

from tests.eval.eval_cases import RAG_TEST_CASES, AGENT_TEST_CASES
from src.lib.evaluator import RAGEvaluator, EvalReport


def _separator(title: str) -> None:
    width = 72
    pad = (width - len(title) - 2) // 2
    print(f"\n{'=' * pad} {title} {'=' * pad}")


def run_rag(evaluator: RAGEvaluator, threshold: float, delay: float) -> EvalReport:
    _separator("RAG EVALUATION SUITE")
    print(
        f"  Cases: {len(RAG_TEST_CASES)}  |  Threshold: {threshold}/5.0  |  Delay: {delay}s\n"
    )
    report = evaluator.run_rag_suite(
        RAG_TEST_CASES, threshold=threshold, delay_between=delay
    )

    for r in report.results:
        status = "PASS" if r["passed"] else "FAIL"
        m = r.get("metrics", {})
        print(
            f"  [{status}] {r['label']:<30} overall={m.get('overall', 0):.2f}"
            f"  faith={m.get('faithfulness', 0):.1f}  ctx={m.get('context_relevance', 0):.1f}"
        )

    print(f"\n{report.summary()}")
    return report


def run_agent(evaluator: RAGEvaluator, threshold: float) -> None:
    _separator("AGENT EVALUATION SUITE")
    print(f"  Cases: {len(AGENT_TEST_CASES)}  |  Threshold: {threshold}/5.0\n")
    passed = failed = 0

    for tc in AGENT_TEST_CASES:
        m = evaluator.evaluate_agent(
            query=tc["query"],
            answer=tc.get("expected_answer", ""),
            tool_calls=tc.get("tool_calls", []),
            expected_answer=tc.get("expected_answer"),
        )
        status = "PASS" if m.passed(threshold) else "FAIL"
        if m.passed(threshold):
            passed += 1
        else:
            failed += 1
        print(
            f"  [{status}] {tc['label']:<30} overall={m.overall:.2f}  "
            f"quality={m.response_quality:.1f}  grounding={m.factual_grounding:.1f}"
        )
        time.sleep(0.3)

    _separator("AGENT SUMMARY")
    print(f"  Total: {passed + failed}  |  Passed: {passed}  |  Failed: {failed}")
    print(f"  Pass rate: {100 * passed / (passed + failed):.0f}%\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run RAG and/or agent evaluation suites"
    )
    parser.add_argument("--rag", action="store_true", help="Run RAG suite only")
    parser.add_argument("--agent", action="store_true", help="Run agent suite only")
    parser.add_argument(
        "--threshold", type=float, default=3.0, help="Pass/fail threshold (default 3.0)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds between LLM calls (default 0.5)",
    )
    args = parser.parse_args()

    run_both = not args.rag and not args.agent

    evaluator = RAGEvaluator()

    rag_passed = True
    if args.rag or run_both:
        report = run_rag(evaluator, threshold=args.threshold, delay=args.delay)
        rag_passed = report.failed == 0

    if args.agent or run_both:
        run_agent(evaluator, threshold=args.threshold)

    if not rag_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
