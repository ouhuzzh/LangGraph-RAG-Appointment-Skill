import argparse
import json
from pathlib import Path

from db.retrieval_log_store import RetrievalLogStore


def _render_text_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "Retrieval Quality Summary",
        f"- sample_count: {summary['sample_count']}",
        f"- retry_rate: {summary['retry_rate']}",
        f"- multi_query_rate: {summary['multi_query_rate']}",
        f"- no_evidence_rate: {summary['no_evidence_rate']}",
        f"- low_confidence_rate: {summary['low_confidence_rate']}",
        f"- avg_query_plan_size: {summary['avg_query_plan_size']}",
        f"- avg_result_count: {summary['avg_result_count']}",
        f"- avg_retry_count: {summary['avg_retry_count']}",
        f"- confidence_distribution: {summary['confidence_distribution']}",
        f"- sufficiency_distribution: {summary['sufficiency_distribution']}",
        "",
        "Recent Retrieval Events",
    ]
    for item in report["events"]:
        lines.extend(
            [
                f"[{item['timestamp']}] {item['query_text']}",
                f"  rewritten={item['rewritten_query'] or 'n/a'} mode={item['retrieval_mode'] or 'n/a'} top_k={item['top_k']} results={item['result_count']}",
                f"  confidence={item['final_confidence_bucket'] or 'n/a'} sufficiency={item['sufficiency_result'] or 'n/a'} retries={item['retry_count']}",
                f"  query_plan={item['query_plan']}",
            ]
        )
    return "\n".join(lines)


def _render_markdown_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Retrieval Quality Report",
        "",
        "## Summary",
        f"- Sample count: {summary['sample_count']}",
        f"- Retry rate: {summary['retry_rate']}",
        f"- Multi-query rate: {summary['multi_query_rate']}",
        f"- No-evidence rate: {summary['no_evidence_rate']}",
        f"- Low-confidence rate: {summary['low_confidence_rate']}",
        f"- Avg query plan size: {summary['avg_query_plan_size']}",
        f"- Avg result count: {summary['avg_result_count']}",
        f"- Avg retry count: {summary['avg_retry_count']}",
        "",
        "## Distributions",
        "",
        f"- Confidence buckets: `{summary['confidence_distribution']}`",
        f"- Sufficiency results: `{summary['sufficiency_distribution']}`",
        "",
        "## Recent Retrieval Events",
        "",
        "| Timestamp | Query | Confidence | Sufficiency | Retry Count | Query Plan |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["events"]:
        query = (item["query_text"] or "").replace("\n", " ").replace("|", "\\|")
        query_plan = ", ".join(item.get("query_plan") or []).replace("|", "\\|")
        lines.append(
            f"| {item['timestamp']} | {query} | {item['final_confidence_bucket'] or 'n/a'} | "
            f"{item['sufficiency_result'] or 'n/a'} | {item['retry_count']} | {query_plan or 'n/a'} |"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render a recent retrieval quality report from persisted retrieval logs.")
    parser.add_argument("--limit", type=int, default=50, help="How many recent retrieval events to include.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report.")
    parser.add_argument("--output", help="Optional path to write the rendered report.")
    args = parser.parse_args(argv)

    report = RetrievalLogStore().build_recent_report(limit=args.limit)

    if args.json:
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
    elif args.markdown:
        rendered = _render_markdown_report(report)
    else:
        rendered = _render_text_report(report)

    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
