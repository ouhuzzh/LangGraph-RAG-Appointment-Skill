import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from benchmarks.resume_benchmarks import (
    InMemoryHybridBenchmarkCollection,
    KeywordBenchmarkEmbeddings,
    as_pretty_json,
    build_isolated_medical_corpora,
    evaluate_medical_rag_benchmark,
    evaluate_offline_answer_benchmark,
    evaluate_memory_token_benchmark,
    load_medical_rag_benchmark_samples,
    load_memory_benchmark_samples,
    load_offline_answer_benchmark_samples,
)
from core.qa_eval import RetrievalQualityEvaluator, load_qa_samples
from db.vector_db_manager import VectorDbManager

MEMORY_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "memory_benchmark_samples.json"
MEDICAL_RAG_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "medical_rag_benchmark_samples.json"
QA_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "qa_eval_samples.json"
QA_ANSWERS_PATH = REPO_ROOT / "tests" / "fixtures" / "qa_eval_answers.json"
OFFLINE_ANSWER_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "offline_answer_benchmark_samples.json"


def _resolve_doc_paths() -> list[Path]:
    markdown_dir = REPO_ROOT / "markdown_docs"
    doc_paths = []
    for pattern in ("who-*.md", "nhc-*.md"):
        doc_paths.extend(sorted(markdown_dir.glob(pattern)))
    unique = []
    seen = set()
    for path in doc_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _load_answer_map(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Answer file must be a JSON object mapping sample id to answer text.")
    return {str(key): str(value) for key, value in payload.items()}


def _run_live_answer_eval(limit: int = 3, score_threshold: float = 0.7) -> dict:
    vector_db = VectorDbManager()
    vector_db.create_collection(config.CHILD_COLLECTION)
    stats = vector_db.get_collection_stats()
    if stats.get("child_chunks", 0) == 0:
        return {
            "enabled": False,
            "status": "skipped_empty_kb",
            "reason": "Knowledge base is empty.",
        }

    samples = load_qa_samples(QA_SAMPLES_PATH)
    answer_map = _load_answer_map(QA_ANSWERS_PATH)
    evaluator = RetrievalQualityEvaluator(
        vector_db.get_collection(config.CHILD_COLLECTION),
        limit=limit,
        score_threshold=score_threshold,
    )
    report = evaluator.evaluate_samples(samples, answer_provider=lambda sample: answer_map.get(sample.sample_id))
    summary = report.get("summary", {})
    return {
        "enabled": True,
        "status": "ok",
        "summary": {
            "sample_count": summary.get("sample_count"),
            "avg_overall_score": summary.get("avg_overall_score"),
            "avg_answer_score": summary.get("avg_answer_score"),
            "avg_safety_score": summary.get("avg_safety_score"),
            "avg_tone_score": summary.get("avg_tone_score"),
            "pass_rate_085": summary.get("pass_rate_085"),
            "route_hit_rate": summary.get("route_hit_rate"),
            "retrieval_relevance_hit_rate": summary.get("retrieval_relevance_hit_rate"),
            "evidence_sufficiency_pass_rate": summary.get("evidence_sufficiency_pass_rate"),
            "grounding_violation_rate": summary.get("grounding_violation_rate"),
        },
        "low_scoring_samples": summary.get("low_scoring_samples", []),
    }


def build_acceptance_report(include_live_qa: bool = False) -> dict:
    memory_samples = load_memory_benchmark_samples(MEMORY_SAMPLES_PATH)
    memory_report = evaluate_memory_token_benchmark(memory_samples)

    doc_paths = _resolve_doc_paths()
    if not doc_paths:
        raise ValueError("No benchmark markdown documents found under markdown_docs/.")
    rag_samples = load_medical_rag_benchmark_samples(MEDICAL_RAG_SAMPLES_PATH)
    baseline_docs, optimized_docs = build_isolated_medical_corpora(doc_paths)
    embeddings = KeywordBenchmarkEmbeddings()
    baseline_collection = InMemoryHybridBenchmarkCollection(baseline_docs, embeddings)
    optimized_collection = InMemoryHybridBenchmarkCollection(optimized_docs, embeddings)
    retrieval_report = evaluate_medical_rag_benchmark(rag_samples, baseline_collection, optimized_collection)
    offline_answer_samples = load_offline_answer_benchmark_samples(OFFLINE_ANSWER_SAMPLES_PATH)
    offline_answer_report = evaluate_offline_answer_benchmark(
        offline_answer_samples,
        baseline_collection,
        optimized_collection,
    )

    acceptance_summary = {
        "memory_token_reduction_avg": memory_report["summary"]["avg_token_reduction_rate"],
        "memory_token_reduction_p95": memory_report["summary"]["p95_token_reduction_rate"],
        "retrieval_precision_at_5_baseline": retrieval_report["summary"]["baseline_precision_at_5"],
        "retrieval_precision_at_5_optimized": retrieval_report["summary"]["optimized_precision_at_5"],
        "retrieval_precision_at_5_uplift": retrieval_report["summary"]["precision_uplift"],
        "retrieval_recall_at_5_baseline": retrieval_report["summary"]["baseline_recall_at_5"],
        "retrieval_recall_at_5_optimized": retrieval_report["summary"]["optimized_recall_at_5"],
        "retrieval_mrr_at_10_baseline": retrieval_report["summary"]["baseline_mrr_at_10"],
        "retrieval_mrr_at_10_optimized": retrieval_report["summary"]["optimized_mrr_at_10"],
        "offline_answer_score_baseline": offline_answer_report["summary"]["baseline_avg_answer_score"],
        "offline_answer_score_optimized": offline_answer_report["summary"]["optimized_avg_answer_score"],
        "offline_answer_score_uplift": offline_answer_report["summary"]["answer_score_uplift"],
        "offline_citation_precision_baseline": offline_answer_report["summary"]["baseline_avg_citation_precision"],
        "offline_citation_precision_optimized": offline_answer_report["summary"]["optimized_avg_citation_precision"],
    }

    live_qa = None
    if include_live_qa:
        try:
            live_qa = _run_live_answer_eval()
        except Exception as exc:
            live_qa = {
                "enabled": False,
                "status": "error",
                "reason": str(exc),
            }

    return {
        "summary": acceptance_summary,
        "memory_benchmark": memory_report,
        "retrieval_benchmark": retrieval_report,
        "offline_answer_benchmark": offline_answer_report,
        "live_answer_eval": live_qa,
    }


def _render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Acceptance Benchmark Report",
        "",
        "## Executive Summary",
        f"- Memory token reduction avg: {summary['memory_token_reduction_avg']}",
        f"- Memory token reduction P95: {summary['memory_token_reduction_p95']}",
        f"- Retrieval Precision@5: {summary['retrieval_precision_at_5_baseline']} -> {summary['retrieval_precision_at_5_optimized']}",
        f"- Retrieval Recall@5: {summary['retrieval_recall_at_5_baseline']} -> {summary['retrieval_recall_at_5_optimized']}",
        f"- Retrieval MRR@10: {summary['retrieval_mrr_at_10_baseline']} -> {summary['retrieval_mrr_at_10_optimized']}",
        f"- Offline answer score: {summary['offline_answer_score_baseline']} -> {summary['offline_answer_score_optimized']}",
        f"- Offline citation precision: {summary['offline_citation_precision_baseline']} -> {summary['offline_citation_precision_optimized']}",
        "",
        "## Memory Benchmark",
        "",
        f"- Sample count: {report['memory_benchmark']['summary']['sample_count']}",
        f"- Avg baseline tokens: {report['memory_benchmark']['summary']['avg_baseline_tokens']}",
        f"- Avg optimized tokens: {report['memory_benchmark']['summary']['avg_optimized_tokens']}",
        f"- Avg reduction rate: {report['memory_benchmark']['summary']['avg_token_reduction_rate']}",
        f"- P95 reduction rate: {report['memory_benchmark']['summary']['p95_token_reduction_rate']}",
        "",
        "## Retrieval Benchmark",
        "",
        f"- Sample count: {report['retrieval_benchmark']['summary']['sample_count']}",
        f"- Baseline Precision@5: {report['retrieval_benchmark']['summary']['baseline_precision_at_5']}",
        f"- Optimized Precision@5: {report['retrieval_benchmark']['summary']['optimized_precision_at_5']}",
        f"- Baseline Recall@5: {report['retrieval_benchmark']['summary']['baseline_recall_at_5']}",
        f"- Optimized Recall@5: {report['retrieval_benchmark']['summary']['optimized_recall_at_5']}",
        f"- Baseline MRR@10: {report['retrieval_benchmark']['summary']['baseline_mrr_at_10']}",
        f"- Optimized MRR@10: {report['retrieval_benchmark']['summary']['optimized_mrr_at_10']}",
        "",
        "## Offline Answer Benchmark",
        "",
        f"- Sample count: {report['offline_answer_benchmark']['summary']['sample_count']}",
        f"- Baseline avg answer score: {report['offline_answer_benchmark']['summary']['baseline_avg_answer_score']}",
        f"- Optimized avg answer score: {report['offline_answer_benchmark']['summary']['optimized_avg_answer_score']}",
        f"- Answer score uplift: {report['offline_answer_benchmark']['summary']['answer_score_uplift']}",
        f"- Baseline avg citation precision: {report['offline_answer_benchmark']['summary']['baseline_avg_citation_precision']}",
        f"- Optimized avg citation precision: {report['offline_answer_benchmark']['summary']['optimized_avg_citation_precision']}",
        "",
    ]
    live_qa = report.get("live_answer_eval")
    if live_qa:
        lines.extend(["## Live Answer-Level QA", ""])
        lines.append(f"- Status: {live_qa.get('status')}")
        if live_qa.get("summary"):
            for key, value in live_qa["summary"].items():
                lines.append(f"- {key}: {value}")
        if live_qa.get("reason"):
            lines.append(f"- Reason: {live_qa['reason']}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a more formal acceptance-style benchmark report for memory, retrieval, and optional answer-level QA.")
    parser.add_argument("--include-live-qa", action="store_true", help="Also run live answer-level QA evaluation against the current PostgreSQL-backed knowledge base.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--output", help="Optional output file path.")
    args = parser.parse_args(argv)

    report = build_acceptance_report(include_live_qa=args.include_live_qa)
    rendered = as_pretty_json(report) if args.json else _render_markdown(report)
    print(rendered)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
