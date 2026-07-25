"""Test scorecard — run the suite grouped by product dimension and emit metrics.

Categorizes the flat ``tests/`` directory into product dimensions (safety,
retrieval, routing, appointment, memory, api, quality, frontend-agnostic core)
without moving any files, then runs each category and prints a scorecard:

    python scripts/test_scorecard.py            # markdown table
    python scripts/test_scorecard.py --json     # machine-readable

Useful for quantifying per-dimension coverage/health instead of one opaque
"N tests OK" number.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "project"))

# Ordered keyword -> category mapping; first match wins, unmatched -> "core".
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("safety", (
        "clinical_safety", "boundary_e2e", "auth_security", "runtime_security",
        "crypto", "audit_log", "schema_guard",
    )),
    ("retrieval", (
        "agentic_retrieval", "retrieval", "knowledge_graph", "contextual",
        "semantic_cache", "medical_source", "nhc_pdf", "who_html",
        "document", "official", "kb", "knowledge_base", "pdf_conversion",
    )),
    ("routing", (
        "intent", "routing", "turn_planner", "skill", "task_decomposition",
        "mcp_routing", "answer_reflection", "nodes_helpers", "date_utils",
        "classifiers",
    )),
    ("appointment", ("appointment", "mcp_reachability", "worker_deployment")),
    ("memory", (
        "memory", "redis", "context_compression", "persistent_checkpointer",
        "checkpointer",
    )),
    ("api", (
        "api_app", "session_locks", "startup_smoke", "chat_interface",
        "chat_turn", "sse", "genui", "service_bootstrapper", "storage_and_services",
        "live_db",
    )),
    ("quality", (
        "qa_eval", "dialogue_quality", "quality", "report", "ablation",
        "benchmark", "transcript", "self_eval", "online",
    )),
    ("ops", ("prod", "validate", "docker", "deployment", "jobs")),
]


def categorize(module_name: str) -> str:
    stripped = module_name.removeprefix("test_")
    for category, keywords in CATEGORY_RULES:
        if any(keyword in stripped for keyword in keywords):
            return category
    return "core"


def discover_modules() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        module = path.stem
        groups.setdefault(categorize(module), []).append(f"tests.{module}")
    return groups


def run_category(modules: list[str]) -> dict:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for module in modules:
        suite.addTests(loader.loadTestsFromName(module))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    started = time.perf_counter()
    result = runner.run(suite)
    duration = time.perf_counter() - started
    return {
        "modules": len(modules),
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "duration_s": round(duration, 2),
        "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-dimension test scorecard")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = parser.parse_args()

    groups = discover_modules()
    scorecard: dict[str, dict] = {}
    for category in sorted(groups):
        scorecard[category] = run_category(groups[category])

    totals = {
        key: sum(entry[key] for entry in scorecard.values())
        for key in ("modules", "tests", "passed", "failures", "errors", "skipped")
    }
    totals["duration_s"] = round(sum(entry["duration_s"] for entry in scorecard.values()), 2)

    if args.json:
        print(json.dumps({"categories": scorecard, "totals": totals}, indent=2))
    else:
        print("| Dimension | Modules | Tests | Passed | Failed | Errors | Skipped | Time (s) |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for category, entry in scorecard.items():
            print(
                f"| {category} | {entry['modules']} | {entry['tests']} | {entry['passed']} "
                f"| {entry['failures']} | {entry['errors']} | {entry['skipped']} | {entry['duration_s']} |"
            )
        print(
            f"| **total** | **{totals['modules']}** | **{totals['tests']}** | **{totals['passed']}** "
            f"| **{totals['failures']}** | **{totals['errors']}** | **{totals['skipped']}** | **{totals['duration_s']}** |"
        )

    return 1 if (totals["failures"] or totals["errors"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
