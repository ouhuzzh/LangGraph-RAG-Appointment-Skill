import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.resume_benchmarks import (
    as_pretty_json,
    evaluate_memory_token_benchmark,
    load_memory_benchmark_samples,
)

DEFAULT_SAMPLES_PATH = REPO_ROOT / "tests" / "fixtures" / "memory_benchmark_samples.json"


def _print_text_report(report: dict):
    summary = report["summary"]
    print("Memory Token Benchmark")
    print(f"- sample_count: {summary['sample_count']}")
    print(f"- avg_baseline_tokens: {summary['avg_baseline_tokens']}")
    print(f"- avg_optimized_tokens: {summary['avg_optimized_tokens']}")
    print(f"- avg_token_reduction_rate: {summary['avg_token_reduction_rate']}")
    print(f"- p95_baseline_tokens: {summary['p95_baseline_tokens']}")
    print(f"- p95_optimized_tokens: {summary['p95_optimized_tokens']}")
    print(f"- p95_token_reduction_rate: {summary['p95_token_reduction_rate']}")
    print(f"- short_term_window_messages: {summary['short_term_window_messages']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark token savings for the hybrid memory strategy versus full-history prompts.")
    parser.add_argument("--samples", default=str(DEFAULT_SAMPLES_PATH), help="Path to benchmark sample JSON.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args(argv)

    samples = load_memory_benchmark_samples(args.samples)
    report = evaluate_memory_token_benchmark(samples)
    if args.json:
        print(as_pretty_json(report))
    else:
        _print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
