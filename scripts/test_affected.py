#!/usr/bin/env python
"""Run only the tests affected by current git changes.

Usage:
    python scripts/test_affected.py          # uses uncommitted changes (staged + unstaged)
    python scripts/test_affected.py --staged # only staged changes
    python scripts/test_affected.py --commit HEAD~1  # changes since a specific commit
"""

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

# Module prefix -> list of test module names (without 'tests.' prefix)
MODULE_TEST_MAP: dict[str, list[str]] = {
    "project/rag_agent/": [
        "test_agentic_retrieval",
        "test_routing_edges",
        "test_answer_reflection",
        "test_turn_planner",
        "test_dialogue_quality",
        "test_boundary_e2e",
        "test_nodes_helpers",
        "test_clinical_safety",
        "test_persistent_checkpointer",
        "test_intent_pipeline",
        "test_intent_embedder",
        "test_task_decomposition",
    ],
    "project/core/": [
        "test_chat_interface",
        "test_chat_turn_service",
        "test_chat_turn_input_service",
        "test_document_manager",
        "test_document_parsers",
        "test_document_metadata_flow",
        "test_contextual_retrieval",
        "test_context_compression",
        "test_knowledge_base_supervisor",
        "test_knowledge_base_worker",
        "test_rag_system_status",
        "test_rag_system_import_history",
        "test_document_source_catalog",
        "test_skill_bootstrapper",
        "test_service_bootstrapper",
    ],
    "project/api/": [
        "test_api_app",
        "test_auth_security",
        "test_session_locks",
    ],
    "project/skills/": [
        "test_skill_registry",
        "test_skill_bootstrapper",
        "test_appointment_skill",
    ],
    "project/memory/": [
        "test_redis_memory",
        "test_user_memory_store",
        "test_memory_extractor",
        "test_memory_retrieval_optimization",
        "test_storage_and_services",
    ],
    "project/db/": [
        "test_live_db_integration",
        "test_document_ids",
        "test_schema_guard",
        "test_semantic_cache",
        "test_knowledge_graph",
        "test_retrieval_log_report",
        "test_route_quality_report",
        "test_audit_log",
    ],
    "project/services/": [
        "test_appointment_skill",
        "test_appointment_flow",
        "test_storage_and_services",
    ],
    "project/mcp_integration/": [
        "test_mcp_reachability",
        "test_mcp_routing_fixes",
    ],
    "project/llm_tiered_router.py": [
        "test_llm_tiered_router",
    ],
    "project/config.py": [
        "test_startup_smoke",
    ],
    "project/worker.py": [
        "test_worker_deployment",
    ],
    "project/benchmarks/": [
        "test_resume_benchmarks",
        "test_qa_eval",
        "test_ablation",
    ],
    "scripts/": [
        "test_check_prod_host",
        "test_validate_prod_env",
        "test_prod_acceptance_check",
    ],
}


def get_changed_files(staged_only: bool = False, commit: str | None = None) -> list[str]:
    """Return list of changed file paths (posix-style, relative to repo root)."""
    if commit:
        cmd = ["git", "diff", "--name-only", commit]
    elif staged_only:
        cmd = ["git", "diff", "--name-only", "--cached"]
    else:
        # Uncommitted: staged + unstaged vs HEAD
        cmd = ["git", "diff", "--name-only", "HEAD"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        # Fallback: if HEAD doesn't exist (initial commit), show staged
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_tests(changed_files: list[str]) -> list[str]:
    """Map changed files to affected test modules."""
    test_set: set[str] = set()
    frontend_changed = False

    for filepath in changed_files:
        path = PurePosixPath(filepath)

        # Direct test file edits — include themselves
        if str(path).startswith("tests/") and path.name.startswith("test_"):
            test_set.add(path.stem)
            continue

        # Frontend changes
        if str(path).startswith("frontend/"):
            frontend_changed = True
            continue

        # Match against module prefixes
        for prefix, tests in MODULE_TEST_MAP.items():
            if str(path).startswith(prefix) or filepath.startswith(prefix):
                test_set.update(tests)

    return sorted(test_set), frontend_changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tests affected by current changes.")
    parser.add_argument("--staged", action="store_true", help="Only consider staged changes")
    parser.add_argument("--commit", type=str, default=None, help="Diff against a specific commit (e.g. HEAD~1)")
    parser.add_argument("--dry-run", action="store_true", help="Print test modules without running")
    args = parser.parse_args()

    changed_files = get_changed_files(staged_only=args.staged, commit=args.commit)

    if not changed_files:
        print("No changed files detected.")
        return 0

    print(f"Changed files ({len(changed_files)}):")
    for f in changed_files:
        print(f"  {f}")
    print()

    test_modules, frontend_changed = resolve_tests(changed_files)

    if frontend_changed:
        print("Frontend changes detected → run: cd frontend && npm run build")
        print()

    if not test_modules:
        print("No backend test modules affected.")
        return 0

    # Build unittest command
    module_args = [f"tests.{m}" for m in test_modules]
    print(f"Affected test modules ({len(test_modules)}):")
    for m in module_args:
        print(f"  {m}")
    print()

    if args.dry_run:
        print("Dry run — not executing tests.")
        return 0

    cmd = [sys.executable, "-m", "unittest"] + module_args + ["-v"]
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
