import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.resume_benchmarks import (
    InMemoryHybridBenchmarkCollection,
    KeywordBenchmarkEmbeddings,
    as_pretty_json,
    build_isolated_medical_corpora,
    evaluate_medical_rag_benchmark,
    load_medical_rag_benchmark_samples,
)

DEFAULT_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "medical_rag_benchmark_samples.json"
DEFAULT_DOC_PATTERNS = ("who-*.md", "nhc-*.md")


def _resolve_doc_paths(root: Path) -> list[Path]:
    docs = []
    markdown_dir = root / "markdown_docs"
    for pattern in DEFAULT_DOC_PATTERNS:
        docs.extend(sorted(markdown_dir.glob(pattern)))
    unique = []
    seen = set()
    for path in docs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _print_text_report(report: dict):
    summary = report["summary"]
    print("Medical RAG Benchmark")
    print(f"- sample_count: {summary['sample_count']}")
    print(f"- baseline_precision_at_5: {summary['baseline_precision_at_5']}")
    print(f"- baseline_recall_at_5: {summary['baseline_recall_at_5']}")
    print(f"- baseline_mrr_at_10: {summary['baseline_mrr_at_10']}")
    print(f"- baseline_hit_at_5: {summary['baseline_hit_at_5']}")
    print(f"- optimized_precision_at_5: {summary['optimized_precision_at_5']}")
    print(f"- optimized_recall_at_5: {summary['optimized_recall_at_5']}")
    print(f"- optimized_mrr_at_10: {summary['optimized_mrr_at_10']}")
    print(f"- optimized_hit_at_5: {summary['optimized_hit_at_5']}")
    print(f"- precision_uplift: {summary['precision_uplift']}")
    print(f"- recall_uplift: {summary['recall_uplift']}")
    print(f"- mrr_uplift: {summary['mrr_uplift']}")
    print(f"- keyword_coverage_uplift: {summary['keyword_coverage_uplift']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark baseline versus optimized medical RAG retrieval on an isolated NHC/WHO corpus.")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES_PATH), help="Path to benchmark sample JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args(argv)

    doc_paths = _resolve_doc_paths(REPO_ROOT)
    if not doc_paths:
        raise SystemExit("No markdown benchmark documents found under markdown_docs/.")

    samples = load_medical_rag_benchmark_samples(args.samples)
    baseline_docs, optimized_docs = build_isolated_medical_corpora(doc_paths)
    embeddings = KeywordBenchmarkEmbeddings()
    baseline_collection = InMemoryHybridBenchmarkCollection(baseline_docs, embeddings)
    optimized_collection = InMemoryHybridBenchmarkCollection(optimized_docs, embeddings)
    report = evaluate_medical_rag_benchmark(samples, baseline_collection, optimized_collection)

    if args.json:
        print(as_pretty_json(report))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
