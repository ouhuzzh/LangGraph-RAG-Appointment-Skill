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
    evaluate_offline_answer_benchmark,
    load_offline_answer_benchmark_samples,
)
DEFAULT_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "offline_answer_benchmark_samples.json"


def _resolve_doc_paths() -> list[Path]:
    markdown_dir = REPO_ROOT / "markdown_docs"
    docs = []
    for pattern in ("who-*.md", "nhc-*.md"):
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
    print("Offline Answer Benchmark")
    print(f"- sample_count: {summary['sample_count']}")
    print(f"- baseline_avg_answer_score: {summary['baseline_avg_answer_score']}")
    print(f"- optimized_avg_answer_score: {summary['optimized_avg_answer_score']}")
    print(f"- answer_score_uplift: {summary['answer_score_uplift']}")
    print(f"- baseline_avg_overall_score: {summary['baseline_avg_overall_score']}")
    print(f"- optimized_avg_overall_score: {summary['optimized_avg_overall_score']}")
    print(f"- overall_score_uplift: {summary['overall_score_uplift']}")
    print(f"- baseline_avg_citation_precision: {summary['baseline_avg_citation_precision']}")
    print(f"- optimized_avg_citation_precision: {summary['optimized_avg_citation_precision']}")
    print(f"- citation_precision_uplift: {summary['citation_precision_uplift']}")
    print(f"- baseline_grounding_violation_rate: {summary['baseline_grounding_violation_rate']}")
    print(f"- optimized_grounding_violation_rate: {summary['optimized_grounding_violation_rate']}")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Evaluate offline answer quality on the isolated NHC/WHO benchmark corpus.")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES_PATH), help="Path to offline answer benchmark samples.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args(argv)

    doc_paths = _resolve_doc_paths()
    if not doc_paths:
        raise SystemExit("No benchmark markdown documents found under markdown_docs/.")

    samples = load_offline_answer_benchmark_samples(args.samples)
    baseline_docs, optimized_docs = build_isolated_medical_corpora(doc_paths)
    embeddings = KeywordBenchmarkEmbeddings()
    baseline_collection = InMemoryHybridBenchmarkCollection(baseline_docs, embeddings)
    optimized_collection = InMemoryHybridBenchmarkCollection(optimized_docs, embeddings)
    report = evaluate_offline_answer_benchmark(samples, baseline_collection, optimized_collection)

    if args.json:
        print(as_pretty_json(report))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
