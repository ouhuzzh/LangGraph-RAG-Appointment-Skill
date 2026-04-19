import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.route_log_store import RouteLogStore


def _render_text_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "Route Quality Summary",
        f"- sample_count: {summary['sample_count']}",
        f"- compound_request_rate: {summary['compound_request_rate']}",
        f"- pending_resume_rate: {summary['pending_resume_rate']}",
        f"- checkpoint_resume_rate: {summary['checkpoint_resume_rate']}",
        f"- secondary_turn_completion_rate: {summary['secondary_turn_completion_rate']}",
        f"- deferred_question_rate: {summary['deferred_question_rate']}",
        f"- intent_distribution: {summary['intent_distribution']}",
        f"- secondary_intent_distribution: {summary['secondary_intent_distribution']}",
        f"- decision_source_distribution: {summary['decision_source_distribution']}",
        "",
        "Recent Route Events",
    ]
    for item in report["events"]:
        lines.extend(
            [
                f"[{item['timestamp']}] {item['user_query']}",
                f"  primary={item['primary_intent'] or 'n/a'} secondary={item['secondary_intent'] or 'n/a'} source={item['decision_source'] or 'n/a'}",
                f"  reason={item['route_reason'] or 'n/a'} pending={item['had_pending_state']}",
            ]
        )
        extra = item.get("extra_metadata") or {}
        if extra.get("topic_focus") or extra.get("deferred_user_question"):
            lines.append(
                f"  topic_focus={extra.get('topic_focus') or 'n/a'} deferred={extra.get('deferred_user_question') or 'n/a'}"
            )
    return "\n".join(lines)


def _render_markdown_report(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Route Quality Report",
        "",
        "## Summary",
        f"- Sample count: {summary['sample_count']}",
        f"- Compound request rate: {summary['compound_request_rate']}",
        f"- Pending resume rate: {summary['pending_resume_rate']}",
        f"- Checkpoint resume rate: {summary['checkpoint_resume_rate']}",
        f"- Secondary turn completion rate: {summary['secondary_turn_completion_rate']}",
        f"- Deferred question rate: {summary['deferred_question_rate']}",
        "",
        "## Distributions",
        "",
        f"- Primary intents: `{summary['intent_distribution']}`",
        f"- Secondary intents: `{summary['secondary_intent_distribution']}`",
        f"- Decision sources: `{summary['decision_source_distribution']}`",
        f"- Route reasons: `{summary['route_reason_distribution']}`",
        "",
        "## Recent Route Events",
        "",
        "| Timestamp | Primary | Secondary | Decision Source | Pending | Query |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["events"]:
        query = (item["user_query"] or "").replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {item['timestamp']} | {item['primary_intent'] or 'n/a'} | {item['secondary_intent'] or 'n/a'} | "
            f"{item['decision_source'] or 'n/a'} | {item['had_pending_state']} | {query} |"
        )
        extra = item.get("extra_metadata") or {}
        if extra.get("topic_focus") or extra.get("deferred_user_question"):
            lines.append(
                f"|  | topic={extra.get('topic_focus') or 'n/a'} | deferred={extra.get('deferred_user_question') or 'n/a'} |  |  |  |"
            )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render a recent route quality report from persisted route logs.")
    parser.add_argument("--limit", type=int, default=50, help="How many recent route events to include.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report.")
    parser.add_argument("--output", help="Optional path to write the rendered report.")
    args = parser.parse_args(argv)

    report = RouteLogStore().build_recent_report(limit=args.limit)

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
