# AGENTS.md

This file provides guidance for AI coding agents working with code in this repository.

## Development Commands

```powershell
# Setup
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Start both backend + frontend
.\start_frontend_app.ps1 -Restart -SkipInstall

# Start backend only
.\venv\Scripts\python.exe project\api_app.py        # FastAPI on :8000

# Start frontend only
cd frontend && npm run dev                           # Vite on :5173

# Start Gradio admin console (separate from user app)
.\venv\Scripts\python.exe project\app.py             # Gradio on :7860
```

## Testing

```powershell
# Lint (catches missing imports, unused vars, type mismatches)
.\venv\Scripts\python.exe -m ruff check project tests

# Syntax check (fast)
.\venv\Scripts\python.exe -m compileall project tests

# Full regression
.\venv\Scripts\python.exe -m unittest discover -s tests -v

# Single test module
.\venv\Scripts\python.exe -m unittest tests.test_api_app -v

# Run only tests affected by current changes (auto-detects from git diff)
.\venv\Scripts\python.exe scripts\test_affected.py

# Frontend build check
cd frontend && npm run build

# Split-app smoke (no live model needed)
.\scripts\smoke_split_app.ps1 -SkipChat

# Split-app smoke with live chat (requires model provider)
.\scripts\smoke_split_app.ps1
```

### Module → Test Mapping

When you change files in a module, run the corresponding tests:

| Changed Module | Run These Tests |
|---|---|
| `project/rag_agent/` | `test_agentic_retrieval` `test_routing_edges` `test_answer_reflection` `test_turn_planner` `test_dialogue_quality` `test_boundary_e2e` `test_nodes_helpers` `test_clinical_safety` `test_persistent_checkpointer` `test_intent_pipeline` `test_intent_embedder` `test_task_decomposition` |
| `project/core/` | `test_chat_interface` `test_chat_turn_service` `test_chat_turn_input_service` `test_document_manager` `test_document_parsers` `test_document_metadata_flow` `test_contextual_retrieval` `test_context_compression` `test_knowledge_base_supervisor` `test_knowledge_base_worker` `test_rag_system_status` `test_rag_system_import_history` `test_document_source_catalog` `test_skill_bootstrapper` `test_service_bootstrapper` |
| `project/api/` | `test_api_app` `test_auth_security` `test_session_locks` |
| `project/skills/` | `test_skill_registry` `test_skill_bootstrapper` `test_appointment_skill` |
| `project/memory/` | `test_redis_memory` `test_user_memory_store` `test_memory_extractor` `test_memory_retrieval_optimization` `test_storage_and_services` |
| `project/db/` | `test_live_db_integration` `test_document_ids` `test_schema_guard` `test_semantic_cache` `test_knowledge_graph` `test_retrieval_log_report` `test_route_quality_report` `test_audit_log` |
| `project/services/` | `test_appointment_skill` `test_appointment_flow` `test_storage_and_services` |
| `project/mcp_integration/` | `test_mcp_reachability` `test_mcp_routing_fixes` |
| `project/llm_tiered_router.py` | `test_llm_tiered_router` |
| `project/config.py` | `test_startup_smoke` |
| `project/worker.py` | `test_worker_deployment` |
| `project/benchmarks/` | `test_resume_benchmarks` `test_qa_eval` `test_ablation` |
| `frontend/` | Run `cd frontend && npm run build` |
| `scripts/` | `test_check_prod_host` `test_validate_prod_env` `test_prod_acceptance_check` |

Example — after editing `project/rag_agent/rag_nodes.py`:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_agentic_retrieval tests.test_routing_edges tests.test_answer_reflection -v
```

## Architecture

This is a medical assistant with RAG, appointment booking, and multi-turn memory. Two separate user surfaces share the same backend.

### Request Flow

```
React/Vite (:5173) → FastAPI (:8000) → ChatInterface → LangGraph graph
                                                           ↓
                                         ┌─────────────────┼──────────────────┐
                                         ▼                 ▼                  ▼
                                   Medical RAG      Appointment Skill   Memory/State
                                         ↓                 ↓                  ↓
                                   pgvector+tsvector  PostgreSQL         Redis+PostgreSQL
```

### Backend Entry Points

- `project/api_app.py` — uvicorn launcher for FastAPI (user app)
- `project/app.py` — Gradio admin/debug console
- Both import `project/config.py` which reads `project/.env` for all settings

### Key Modules

**`project/rag_agent/`** — LangGraph workflow (the core intelligence):
- `graph.py` — builds the StateGraph with 20+ nodes, compiled with a checkpointer; integrates skill-registered nodes dynamically
- `graph_state.py` — `State` (main graph) and `AgentState` (subgraph) TypedDicts; `skill_data: Dict[str, Any]` holds per-skill state
- `routing_nodes.py` — intent classification, turn analysis, department recommendation
- `rag_nodes.py` — query rewrite, retrieval orchestration, answer grounding, fallback
- `appointment_nodes.py` — booking/cancellation nodes invoked from the graph
- `edges.py` — conditional edge functions that route between nodes
- `prompts.py` — all LLM prompt templates
- `tools.py` — LangGraph tool definitions
- `node_helpers.py` — shared helper functions (rule-based intent detection, text sanitization)
- `persistent_checkpointer.py` — `PersistentInMemorySaver` that serializes checkpoints to a pkl file

**`project/skills/`** — pluggable skill framework for extensible intent routing:
- `base_skill.py` — `BaseSkill` ABC: each skill declares `name`, `priority`, `intent_label`, `match()`, `register_nodes()`, `register_edges()`, `get_route_targets()`, `get_state_schema()`
- `registry.py` — `SkillRegistry` singleton: `classify_intent()` tries skills in priority order; `register_all_nodes()`/`register_all_edges()` inject into the graph builder
- `greeting_skill.py` — proof-of-concept skill (priority 10), routes greetings to a dedicated handler → END
- `medical_rag_skill.py` — proof-of-concept skill (priority 60), routes medical questions to the existing `rewrite_query` chain
- Enabled via `SKILLS_ENABLED=true` in `.env`; when disabled, graph falls back to hardcoded routing

**`project/llm_tiered_router.py`** — tiered LLM routing with per-provider circuit breaker:
- Light tier (intent classification, query planning) vs strong tier (answer generation, department recommendation)
- Configured via `LLM_TIERS_JSON` env var; degrades to single-tier if unset
- `CircuitBreaker`: closed → open → half_open state machine with failure threshold and recovery timeout

**`project/core/`** — orchestration and infrastructure:
- `chat_interface.py` — `ChatInterface` facade that the API calls; wraps graph invocation, memory, SSE streaming, and document management
- `rag_system.py` — RAG pipeline: embedding, hybrid retrieval, reranking
- `document_manager.py` — document CRUD, chunking, vector storage
- `document_chunker.py` — text splitting with parent-child chunk strategy
- `knowledge_base_sync.py` — official-source sync with content-hash dedup and soft delete
- `medical_source_ingest.py` — MedlinePlus, NHC, WHO importers
- `qa_eval.py` — offline retrieval/answer/route quality evaluator for benchmarking
- `ablation.py` — `AblationStudy` framework: disables pipeline components (rewrite, hybrid, rerank) to measure their independent contribution

**`project/benchmarks/`** — offline evaluation and ablation studies:
- `run_ablation_study.py` — runs ablation across pipeline config variants
- `resume_benchmarks.py` — end-to-end benchmark with resume/summary reporting
- `evaluate_*.py` — individual evaluators for retrieval quality, answer quality, route quality, QA quality, memory tokens, acceptance

**`project/services/appointment_skill/`** — controlled appointment workflow:
- Discovery (departments, doctors, slots) → Planning (preview) → Action (confirm then execute)
- Idempotency protection on booking execution
- Pending state survives mid-workflow interruptions (user can ask a medical question then resume booking)

**`project/api/routes/`** — FastAPI route modules:
- `chat.py` — SSE stream, session management, history
- `documents.py` — upload, list, sync, status
- `system.py` — health, system status

**`project/db/`** — PostgreSQL + pgvector stores, SQL schemas in `db/sql/`

**`project/memory/`** — `RedisSessionMemory` with in-memory fallback; manages recent context, summaries, topic focus, and pending action state

### Frontend

- `frontend/src/pages/` — ChatPage and DocumentsPage (JSX)
- `frontend/src/components/` — UI components (MessageBubble, Composer, ThemeToggle, Sidebar, etc.)
- `frontend/src/hooks/` — React hooks for chat SSE, status polling, document state, theme, search
- `frontend/src/lib/` — API client and SSE helper
- `frontend/src/i18n/` — internationalization
- CSS custom properties only (no framework)
- Vite dev server proxies API calls to FastAPI

### State Management

The system maintains three layers of state:
1. **LangGraph checkpoint** — full graph state persisted to `runtime/langgraph_checkpoints.pkl` (via `PersistentInMemorySaver`)
2. **Redis session memory** — recent N messages, summary, topic focus, pending action (with in-memory fallback)
3. **PostgreSQL** — documents, chunks, appointments, summaries, retrieval logs

## Configuration

All config is env-driven via `project/.env` (copy from `project/.env.example`). Key groups:

| Group | Key Variables |
|-------|--------------|
| LLM | `ACTIVE_LLM_PROVIDER` (deepseek/openai/anthropic/google/ollama), `LLM_MODEL` |
| Tiered LLM | `LLM_TIERS_JSON`, `LLM_FALLBACK_PROVIDER` |
| Skills | `SKILLS_ENABLED` (true/false) |
| Embedding | `ACTIVE_EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` (default: BAAI/bge-m3) |
| RAG | `ENABLE_RERANK`, `ENABLE_HYBRID_RETRIEVAL`, confidence/relevance score thresholds |
| PostgreSQL | `POSTGRES_HOST/PORT/DB/USER/PASSWORD`, `AUTO_BOOTSTRAP_KNOWLEDGE_BASE` |
| Redis | `REDIS_ENABLED`, `REDIS_HOST/PORT`, `SHORT_TERM_WINDOW_SIZE`, `RECENT_CONTEXT_TURNS` |
| KB Sync | `KB_SYNC_OFFICIAL_SOURCES` (medlineplus,nhc,who), `ENABLE_KB_SYNC_SCHEDULER` |
| Observability | `LANGFUSE_ENABLED`, Langfuse keys |

## Conventions

- Commit style: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`)
- Python style: 4-space indent, `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE_CASE` config
- Tests use Python `unittest` framework in `tests/`, named `test_*.py`
- Keep business logic out of UI layer; RAG flow changes go in `project/rag_agent/` or `project/core/`
- When changing workflow behavior, keep prompts (`prompts.py`), schemas (`graph_state.py`), and routing (`edges.py`) aligned
- New intent types should be implemented as skills in `project/skills/` (subclass `BaseSkill`) rather than adding hardcoded routing
- Do not commit `project/.env`, runtime data (`markdown_docs/`, `runtime/`, `parent_store/`, `qdrant_db/`), or `frontend/dist/`

### Core Path (高风险变更区域)

以下文件/模块变更频率高且相互耦合，修改时需确保相关测试全部通过:
- `project/rag_agent/rag_nodes.py`
- `project/rag_agent/edges.py`
- `project/rag_agent/graph.py`
- `project/core/chat_interface.py`
- `project/config.py`

---
Last reviewed: 2026-07-25
