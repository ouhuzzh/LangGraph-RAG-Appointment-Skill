<div align="center">

# 心语医疗助手 · Xinyu Medical Agent

**A production-grade medical AI assistant built with LangGraph — not a RAG demo. A self-correcting agent with agentic retrieval, GraphRAG, cross-session memory, and a booking pipeline hardened the way real reservation systems are: slot holds, DB-level idempotency, and one-click structured confirmation.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
![LangGraph](https://img.shields.io/badge/LangGraph-stateful%20agent-1f6feb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-session%20memory-DC382D?logo=redis&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=111827)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea043.svg)](LICENSE)

**Medical QA · Hybrid Retrieval · Cross-session Memory · Multi-hospital MCP Booking · PII Encryption**

[Quick Start](#quick-start) · [Architecture](#architecture) · [Agentic Pipeline](#agentic-pipeline-p1p5-from-rag-to-agent) · [Key Metrics](#key-metrics) · [API](#api-surface) · [Docs](#documentation)

</div>

![Xinyu Medical Agent](assets/demo.gif)

> One conversation, the whole system: **triage with a department card** → a medical question answered mid-booking (**interruption-safe pending state**) → a preview that **locks the slot for 10 minutes** → **one-click confirmation** validated by ID equality — no keyword guessing on the critical step.

## Key Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| End-to-end P50 latency | 167s | **17s** | **10×** |
| RAG Precision@5 | 0.68 | **0.83** | +22% |
| Top-1 hit rate | 0.61 | **0.79** | +30% |
| 30-turn prompt tokens | baseline | **-27.4%** | summary compression |
| Cross-session fact recall | — | **74%** | pgvector user memory |
| Test suite | — | **738 backend + 50 frontend** | 9-dimension scorecard, CI-gated (ruff + unittest) |

## Why This Project Exists

Most RAG demos answer one question from a few documents. This project is closer to a real assistant product:

- It answers medical questions with retrieval, evidence checks, citations, and safe fallback behavior.
- It remembers user allergies, medications, and history across sessions (pgvector semantic memory + importance scoring + dedup) — and cross-checks answers against known allergies.
- It books appointments the way real reservation systems do: preview **locks the slot** (TTL hold), confirmation is a **button click validated by ID equality**, and a **partial unique index** makes duplicate confirms idempotent even if session state is lost.
- It survives interruptions: ask a medical question mid-booking, come back, and say "确认预约" — a four-layer continuation stack (button → rules → narrow-band LLM arbiter → fallback) resumes the flow, while execution stays behind a deterministic code gate.
- It connects to multiple hospitals via MCP protocol with per-user encrypted credentials and circuit-breaker isolation.
- It encrypts sensitive medical PII at rest (Fernet column-level encryption with key rotation support).
- It ships with 737 regression tests across 9 product dimensions, benchmark scripts, and a 30-persona stress-test framework.

## Feature Highlights

| Area | Capability |
| --- | --- |
| LangGraph orchestration | Declarative Skill plugin framework — 3-layer intent routing (rule + semantic + LLM), add an intent with 1 class |
| Agentic RAG | Self-correcting retrieval: evidence-reflection loop, task decomposition, answer grounding check, online self-evaluation |
| Retrieval quality | Parent-child chunking, hybrid (pgvector + tsvector) + RRF + rerank, plus opt-in **Contextual Retrieval**, **GraphRAG multi-hop**, and a **semantic answer cache** |
| 3-layer memory | Redis sliding window → LLM summary compression → pgvector cross-session semantic recall with importance scoring |
| MCP multi-hospital | Fernet-encrypted per-user credentials, namespaced tool injection, 3-state circuit breaker per hospital |
| Appointment pipeline | Discovery → Preview (**TTL slot hold**) → **Button confirmation** (ID equality) → Execute (**DB-level idempotency**, transactional reschedule); code-gated state machine, not LLM judgment |
| Dialogue continuation | Four-layer stack: structured buttons → keyword+shape rules → narrow-band LLM arbiter → graceful fallback; wrong guesses cost one clarifying turn, never a wrong booking |
| Knowledge base | Local document upload, official source sync (NHC/WHO/MedlinePlus), content-hash update detection, soft delete |
| Security | Graded clinical safety guardrail (red-flag severity + allergy cross-check + prescription-boundary), PII column-level encryption, JWT auth + login lockout, rate limiting, audit log |
| Operations | Postgres-backed LangGraph checkpointer (multi-replica safe), tiered LLM routing with circuit breaker, 9-dimension test scorecard, CI-enforced lint + tests |
| Frontend | Clinical-grade React UI — restrained single-accent design, structured cards with action buttons, responsive, dark-mode, PWA-ready |

## Core Capabilities

### Agentic RAG: From Retrieve to Reason

The medical-QA path is not a single retrieve-then-generate chain. It is a self-correcting agent loop built in five composable stages, each gated by a runtime toggle and covered by compiled-graph integration tests.

```mermaid
flowchart TD
    A([User query]) --> B[analyze_turn]
    B --> C[rewrite_query]
    C --> D[decompose_tasks]
    D --> E[Send × N — parallel sub-questions]
    E --> F[agent subgraph]
    F --> G[hybrid retrieval]
    G --> H{evidence sufficient?}
    H -->|no| I[refine query]
    I --> G
    H -->|yes| J[collect_answer]
    J --> K[grounded answer generation]
    K --> L{grounding check}
    L -->|fail| M[revise_answer]
    M --> L
    L -->|pass| N[self_eval — LLM-as-judge]
    N --> Z([turn end])
```

- **Evidence-reflection retrieval loop** — rewrites and re-searches when evidence is thin.
- **Answer grounding check + rewrite** — detects hallucination and rewrites strictly within retrieved evidence.
- **Task decomposition** — splits compound questions into parallel sub-questions, then merges answers by index.
- **Online self-evaluation** — LLM-as-judge scores safety, accuracy, completeness, and groundedness; low scores append a visible caveat.

See the [Agentic Pipeline (P1–P4)](#agentic-pipeline-p1p4-from-rag-to-agent) section below for the staged implementation, config toggles, and integration tests.

### Three-Tier Memory: Redis + Summary + Semantic

Conversations are remembered at three time scales so the assistant can both stay grounded in the current thread and recall long-term facts.

```mermaid
flowchart LR
    subgraph Short["Short-term"]
        R[Redis sliding window]
    end
    subgraph Medium["Medium-term"]
        S[LLM summary compression]
    end
    subgraph Long["Long-term"]
        E[episodic memory]
        U[user memories]
        F[reflection memories]
    end
    R --> S
    S --> E
    E --> U
    U --> F
```

| Tier | Store | What it keeps |
| --- | --- | --- |
| Short-term | Redis | Recent N messages in the active thread |
| Medium-term | PostgreSQL | LLM-compressed conversation summary |
| Long-term | pgvector | User facts, episodic turns, reflection abstractions with importance scoring |

Result: **-27.4% prompt tokens** at 30 turns and **74% cross-session fact recall**.

### Three-Layer Intent Routing: Rule + Semantic + LLM

Skills replace hardcoded if-else intent chains. Each Skill declares how it wants to be matched and where it routes.

```mermaid
flowchart LR
    Q[User query] --> L1[L1 keywords]
    L1 -->|miss| L2[L2 semantic utterances]
    L2 -->|miss| L3[LLM classifier]
    L1 -->|hit| R[route to graph node]
    L2 -->|hit| R
    L3 -->|hit| R
```

- **L1 keywords** — exact high-confidence action words, O(1) match, no LLM cost.
- **L2 utterances** — embedding centroid over example sentences for semantic similarity.
- **L3 LLM hint** — skill description injected into the LLM intent-classification prompt for fuzzy cases.

Adding a new intent means adding one `BaseSkill` subclass; the core router and graph wiring stay untouched.

## Architecture

```mermaid
flowchart LR
    U["User"] --> FE["React/Vite user app"]
    FE --> API["FastAPI API"]
    API --> CI["ChatInterface"]
    CI --> G["LangGraph workflow"]

    G --> R["Medical RAG"]
    R --> QR["Query rewrite / query planning"]
    QR --> RET["Hybrid retrieval: pgvector + tsvector"]
    RET --> GR["Rerank / evidence grading / grounding"]

    G --> A["Appointment Skill"]
    A --> D["Discovery: departments, doctors, slots"]
    A --> P["Planning: candidates and previews"]
    A --> X["Actions: confirm then execute"]

    G --> M["Memory and state"]
    M --> Redis["Redis recent messages"]
    M --> PG["PostgreSQL summaries, logs, checkpoints"]

    API --> KB["Documents API"]
    KB --> DM["DocumentManager"]
    DM --> Sync["KnowledgeBaseSyncService"]
    Sync --> Store["documents / parent_chunks / child_chunks"]
```

### Runtime Roles

- **React frontend** is the user-facing product surface for chat and lightweight knowledge-base management.
- **FastAPI** exposes chat SSE, system status, Documents APIs, and frontend/backend adapters.
- **Gradio** remains an internal admin console for advanced diagnostics and manual operations.
- **PostgreSQL + pgvector** is the source of truth for documents, chunks, appointments, logs, and summaries.
- **Redis** stores short-term conversational memory and recoverable session state.

## Agentic Pipeline (P1–P4): From RAG to Agent

The medical-QA path is not a single retrieve-then-generate chain - it is a self-correcting agent with four layered behaviors. Each was built as an isolated stage (spec → plan → TDD → review) and ships with a config toggle that rolls back to the previous stage's behavior, plus compiled-graph integration tests proving the loops actually run through LangGraph's state machinery.

```mermaid
flowchart TD
    A([User turn]) --> B["analyze_turn<br/>(intent)"]
    B --> PT["plan_tasks<br/>(compound -> planned_tasks)"]
    PT -->|medical_rag| C["rewrite_query"]
    C --> D["<b>P3</b> decompose_tasks<br/>compound → 1-3 sub-questions"]
    D --> E["Send × N — parallel fan-out"]
    E --> F1["agent subgraph #1"]
    E --> F2["agent subgraph #N"]
    F1 --> G["orchestrator ⇄ tools<br/>(hybrid retrieval)"]
    F2 --> G
    G --> H["<b>P1</b> evaluate_evidence — sufficient?"]
    H -->|refine query & re-search| G
    H -->|yes / exhausted| I["collect_answer"]
    I --> J["grounded_answer_generation<br/>(merge by index)"]
    J --> K["<b>P2</b> answer_grounding_check — grounded?"]
    K -->|not grounded, budget left| L["<b>P2</b> revise_answer<br/>(evidence-bounded rewrite)"]
    L --> K
    K -->|grounded / exhausted| M["<b>P4</b> self_eval - LLM-as-judge<br/>safety · accuracy · completeness · groundedness"]
    M -->|score &lt; 0.6| N["append soft-degrade caveat"]
    M -->|ok| Z([turn end])
    N --> Z
```

| Stage | Agent behavior | Key node(s) | Toggle (default) | What it adds |
| --- | --- | --- | --- | --- |
| **P1** | Retrieval loop | `evaluate_evidence` | `ENABLE_AGENTIC_RETRIEVAL=true` (`MAX_EVIDENCE_ROUNDS=2`) | Evidence-sufficiency reflection — re-searches with a refined query when retrieval is thin |
| **P2** | Answer reflection | `answer_grounding_check` + `revise_answer` | `ENABLE_ANSWER_REFLECTION=true` (`MAX_GROUNDING_ROUNDS=1`) | Grounding critique + evidence-bounded rewrite — no re-retrieval, stays in the answer stage |
| **P3** | Autonomous planning | `decompose_tasks` + `Send×N` | `ENABLE_TASK_DECOMPOSITION=true` (`MAX_SUB_QUESTIONS=3`) | Splits a compound question into independent facets, fans out parallel retrieval, merges by index |
| **P4** | Self-reflection | `self_eval` | `ENABLE_SELF_EVAL=true` (`SELF_EVAL_DEGRADE_THRESHOLD=0.6`) | LLM-as-judge scores the final answer on 4 dimensions; low scores trigger a visible self-deprecating caveat; score + details persist to `route_logs` |

**Turn planner (compound turns):** `analyze_turn` routes every fresh turn to `plan_tasks`, which decomposes cross-intent compound messages (e.g. "挂号皮肤科，顺便问湿疹") into an ordered `planned_tasks` list. `dispatch_next_task` drains them within a single graph invocation via `advance_task` -> `route_to_next_or_gate`, with `completeness_gate` appending a caveat for any unaddressed task. This replaces the earlier rule-based compound split + cross-turn drain queue.

**Engineering guarantees that make it a real agent, not a pipeline:**
- Every stage is **never-raise** — structured-output LLM calls degrade to a safe default (neutral score / FINISH / single-path) on failure, so the graph never hangs.
- **Cross-turn state safety** - `reset_turn_state` (turn start) clears planner task state so a previous turn's planned tasks can't bleed into the next.
- **Reusability** - P3 fans out by reusing P1's retrieval loop as a unit. Each stage composes rather than rewrites.
- **Rollback** - disabling any toggle restores the prior stage's topology; all four are on by default.

Per-stage design specs and implementation plans live in [`docs/superpowers/`](docs/superpowers/). See also the [interview architecture guide](docs/INTERVIEW_PROJECT_ARCHITECTURE_CN.md) and [architecture gallery](docs/INTERVIEW_PROJECT_ARCHITECTURE_GALLERY.html).

### Retrieval & Safety Extensions (opt-in)

Beyond the always-on pipeline, three production-grade extensions ship behind config toggles (default off, fail-open, unit-tested) so you can measure their lift with the bundled ablation harness before turning them on:

| Extension | Toggle (default) | What it adds |
| --- | --- | --- |
| **Contextual Retrieval** | `ENABLE_CONTEXTUAL_RETRIEVAL=false` | Prepends an LLM-written situating sentence to each chunk before embedding (Anthropic Contextual Retrieval), so a stand-alone chunk carries its document context into the vector index |
| **Semantic answer cache** | `ENABLE_SEMANTIC_CACHE=false` | pgvector similarity cache that short-circuits repeat questions to a stored answer; context-dependent turns are refused so multi-turn safety holds |
| **Clinical safety guardrail** | `ENABLE_CLINICAL_SAFETY_GUARDRAIL=false` | Graded red-flag severity (critical / high / moderate) + prescription-boundary detection + **allergy cross-check** (warns when an answer mentions a substance the user's profile marks as an allergen); strictly additive to existing risk inference |
| **GraphRAG** | `ENABLE_GRAPH_RAG=false` | Medical knowledge graph (disease→symptom→department→drug triples) extracted at ingest time; multi-hop graph traversal fused via RRF into the vector search pipeline |
| **Slot hold** | `ENABLE_SLOT_HOLD=false` | Preview-time TTL reservation (`appointment_holds` table): the quota is locked the moment the preview renders, converts on confirm, releases on abort/expiry — closes the preview→confirm race window |
| **LLM continuation arbiter** | `ENABLE_LLM_CONTINUATION_ARBITER=false` | Narrow-band yes/no LLM verdict for short, signal-free replies while a booking is pending ("行，就他了"); routing power only — execution stays code-gated |
| **Postgres checkpointer** | `GRAPH_CHECKPOINT_BACKEND=pickle` | Set to `postgres` for multi-replica-safe LangGraph checkpoints via `PostgresSaver`; fails open to the file-based saver |
| **Generative UI** | always on (heuristic) | Structured `ui-card` SSE events (department cards, risk banners, appointment previews **with confirm/abort action buttons** — clicks post a structured action validated by `confirmation_id` equality, bypassing free-text parsing entirely) |

Each extension is isolated, reversible, and covered by unit tests (`tests/test_contextual_retrieval.py`, `tests/test_semantic_cache.py`, `tests/test_clinical_safety.py`, `tests/test_knowledge_graph.py`, `tests/test_slot_hold.py`, `tests/test_continuation_arbiter.py`, `tests/test_structured_action_channel.py`, `tests/test_checkpointer_backend.py`).

## Typical Workflows

### Medical QA With Evidence

```text
User: 高血压应该注意什么？
Assistant: Answers with lifestyle, monitoring, medication adherence, and follow-up advice, with source references when evidence is available.
```

### Low-Evidence Medical Fallback

```text
User: 感冒发烧怎么办？
Assistant: Gives general medical information, clearly labels that the answer is not sufficiently knowledge-base grounded, and reminds the user to seek care if symptoms worsen.
```

### Controlled Booking (production loop)

```text
User: 我想挂号
Assistant: Shows available departments or asks for symptoms.
User: 呼吸内科
Assistant: Lists available doctors and slots.
User: 我要预约张医生 2026-04-18 下午
Assistant: Locks the slot (10-min TTL hold), renders a preview card with
           [确认预约] [暂不预约] buttons, and waits.
User: (clicks 确认预约)  ← structured action, validated by confirmation_id equality
Assistant: Converts the hold into a booking — no second quota decrement,
           duplicate confirms return the same appointment_no (DB unique index).
```

### Workflow Interruption

```text
User: 我要挂呼吸内科张医生明天下午的号
Assistant: Creates a booking preview.
User: 对了，咳嗽三天了需要拍片吗？
Assistant: Answers the medical question while keeping the pending booking state.
User: 确认预约
Assistant: Resumes and confirms the previous booking.
```

## Quick Start

### 1. Install Dependencies

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

Optional multi-format document parsing:

```powershell
pip install -r requirements-unstructured.txt
```

### 2. Configure Environment

```powershell
Copy-Item project\.env.example project\.env
```

Fill in at least:

- LLM / embedding provider credentials
- PostgreSQL connection settings
- Redis connection settings
- API Bearer token mapping (`API_AUTH_TOKENS_JSON`)

### 3. Start Required Services

You need:

- PostgreSQL with pgvector
- Redis
- one configured LLM / embedding provider

PostgreSQL setup notes are in [docs/POSTGRES_SETUP_CN.md](docs/POSTGRES_SETUP_CN.md).

Development defaults in `project/.env.example` include:

- `demo-admin-token` for the React admin/demo flow
- `demo-user-token` for regular user chat flow

Production note:

- if `REDIS_ENABLED=true` and `APP_ENV!=development`, Redis is required at startup and the API will fail fast instead of silently falling back to in-process memory

### 4. Start the Split Frontend App

```powershell
.\start_frontend_app.ps1 -Restart -SkipInstall
```

Open:

- User frontend: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Manual startup:

```powershell
.\venv\Scripts\python.exe project\api_app.py
```

```powershell
cd frontend
npm run dev
```

### 5. Start the Gradio Admin Console

```powershell
.\venv\Scripts\python.exe project\app.py
```

Open:

- [http://localhost:7860](http://localhost:7860)

Gradio is the admin/debug console. Use it for diagnostics, full knowledge-base management, and development checks. For normal user-facing demos, prefer the React frontend above.

## API Surface

The React app uses these main endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | API liveness check |
| `GET /api/system/status` | Startup and knowledge-base status |
| `POST /api/chat/session` | Create or reuse a thread id |
| `GET /api/chat/history` | Load visible session history |
| `POST /api/chat/clear` | Clear one thread |
| `POST /api/chat/stream` | Authenticated SSE chat stream |
| `GET /api/documents/status` | Knowledge-base status and recent task summary |
| `GET /api/documents/list` | User-facing document list with source, sync status, and freshness metadata |
| `GET /api/documents/tasks` | Recent import/sync task records |
| `GET /api/documents/sources` | Official-source coverage, recommended use, and expansion notes |
| `POST /api/documents/upload` | Upload files and sync them into the knowledge base |
| `POST /api/documents/sync-official` | Sync one official source |

All `/api/*` routes require `Authorization: Bearer <token>`. Document routes are admin-only.

## Knowledge Base Updates

The knowledge base is updateable, not just one-time import:

- local uploads are converted to Markdown when needed
- each document gets a stable `source_key`
- normalized Markdown content is hashed with SHA-256
- unchanged documents are skipped
- changed documents replace their old chunks in place
- missing official-source documents are soft deleted and removed from retrieval
- recent sync tasks are persisted and surfaced through API/UI

Supported official-source importers currently include:

- MedlinePlus
- NHC whitelist PDFs
- WHO whitelist HTML pages

API startup no longer auto-runs knowledge-base background jobs. Run maintenance explicitly when needed:

```powershell
.\venv\Scripts\python.exe project\kb_jobs.py bootstrap
.\venv\Scripts\python.exe project\kb_jobs.py sync-local --soft-delete-missing
.\venv\Scripts\python.exe project\kb_jobs.py sync-official nhc --limit 5
.\venv\Scripts\python.exe project\kb_jobs.py sync-all
```

Docker Compose also starts a dedicated `worker` process. Set the following in
the Compose env file to let that process own automatic maintenance:

```text
AUTO_BOOTSTRAP_KNOWLEDGE_BASE=true
ENABLE_KB_SYNC_SCHEDULER=true
KB_SYNC_INTERVAL_HOURS=24
```

The API container forces its in-process knowledge-base scheduler off, so adding
API replicas does not duplicate scheduled maintenance. The worker reuses the
PostgreSQL advisory lock used by manual jobs.

## Benchmarks

Bundled benchmark snapshots:

- Long-dialogue memory reduced prompt tokens by **27.4% at P95** in the included benchmark fixture.
- Hybrid retrieval improved **Precision@5 from 0.68 to 0.83** on the bundled NHC/WHO-style medical retrieval benchmark.

Benchmark entrypoints:

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_memory_token_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_medical_rag_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_offline_answer_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_acceptance_report.py --json
```

## Testing

Fast checks:

```powershell
.\venv\Scripts\python.exe -m compileall project tests
.\venv\Scripts\python.exe -m unittest tests.test_api_app -v
cd frontend
npm run build
```

Full regression:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Split app smoke:

```powershell
.\scripts\smoke_split_app.ps1 -SkipChat
```

Live chat smoke, if your model provider is configured:

```powershell
.\scripts\smoke_split_app.ps1
```

## Project Structure

```text
project/
  api/                       # FastAPI app, route modules, SSE helpers, DTOs
  core/                      # bootstrap, chat interface, document sync, RAG system
  rag_agent/                 # LangGraph graph, nodes, prompts, tools, state schemas
  skills/                    # pluggable skill framework (BaseSkill + registry)
  services/appointment_skill/# discovery / planning / action skill package
  db/                        # PostgreSQL stores, schema manager, vector DB manager
  memory/                    # Redis memory and summary persistence
  ui/                        # Gradio admin/debug console
  benchmarks/                # memory, retrieval, route, answer-quality benchmarks
frontend/
  src/pages/                 # Chat, Documents, Hospital Binding pages
  src/hooks/                 # chat, status, and documents state hooks
  src/components/            # reusable UI components
  src/styles/                # clinical design system (single accent, dark-mode)
  src/lib/                   # API and SSE helpers
  src/constants/             # frontend constants and status mapping
scripts/                     # smoke and maintenance scripts
tests/                       # unit, regression, and live DB tests
docs/                        # project guide, setup, QA notes
assets/                      # README demo media
```

## Documentation

Start from the [documentation index](docs/README.md) if you are not sure which document to read.

| Area | Documents |
| --- | --- |
| Project overview | [Project structure, Chinese](docs/PROJECT_STRUCTURE_CN.md), [Project guide, Chinese](docs/PROJECT_GUIDE_CN.md), [User guide](docs/USER_GUIDE.md) |
| Development | [Contributing guide](CONTRIBUTING.md), [PostgreSQL setup](docs/POSTGRES_SETUP_CN.md), [QA evaluation guide](docs/QA_EVAL.md) |
| Architecture | [Architecture refactor plan](docs/ARCHITECTURE_REFACTOR_PLAN_CN.md), [MCP tool contract](docs/MCP_TOOL_CONTRACT_CN.md), [Frontend/backend split](docs/architecture/frontend_backend_split.md), [FastAPI API layer notes](project/api/README.md) |
| Deployment | [Docker deployment](docs/DOCKER_DEPLOY_CN.md), [Production rollout checklist](docs/PRODUCTION_ROLLOUT_CHECKLIST_CN.md) |
| Safety | [Security policy](SECURITY.md), [Medical import guide](docs/MEDICAL_IMPORT.md), [Medical sources guide](docs/MEDICAL_SOURCES.md) |
| Interview | [Interview architecture guide](docs/INTERVIEW_PROJECT_ARCHITECTURE_CN.md), [Architecture gallery](docs/INTERVIEW_PROJECT_ARCHITECTURE_GALLERY.html) |

## Data and Repository Hygiene

The repository intentionally does **not** commit runtime data:

- `markdown_docs/`
- `runtime/`
- `output/`
- `parent_store/` and `qdrant_db/` legacy/local runtime stores
- `frontend/dist/`
- `frontend/node_modules/`
- `.env` / `project/.env`

Use `project/.env.example` as the template for local configuration.

## Safety Scope

This is an engineering demo for medical information assistance and workflow orchestration.

It is **not** a medical device, does **not** provide diagnosis, and does **not** replace licensed clinicians. High-risk symptoms, medication-dose questions, and low-evidence answers are handled with more conservative wording and visible safety reminders.

## Roadmap

- ~~Build the agentic pipeline (retrieval loop, answer reflection, task decomposition, online self-eval)~~ - **done (P1–P4)**, see [Agentic Pipeline](#agentic-pipeline-p1p4-from-rag-to-agent)
- ~~Add stronger answer-level evaluation~~ - **done (P4 `self_eval`, LLM-as-judge on safety/accuracy/completeness/groundedness, persisted to `route_logs`)**
- ~~Contextual Retrieval, semantic answer cache, and a graded clinical safety guardrail~~ - **done (P5-P7, opt-in toggles, unit-tested)**
- ~~GraphRAG knowledge graph with multi-hop retrieval~~ - **done (P8, opt-in, unit-tested)**
- ~~Generative UI: structured card events + React card components~~ - **done, including button-based confirmation with `confirmation_id` validation**
- ~~Production booking loop: slot holds, DB-level idempotency, transactional reschedule~~ - **done (opt-in, live-verified against PostgreSQL)**
- ~~Multi-replica-safe graph checkpoints~~ - **done (opt-in `PostgresSaver` backend, fail-open)**
- MCP remote-booking reconciliation: model the timeout-after-success UNKNOWN state and reconcile via `list_appointments` instead of blind retry
- Extend slot holds to the reschedule preview path (currently transactional swap at confirm time only)
- Waitlist / standby queue for fully-booked slots
- Move more admin capabilities from Gradio to dedicated FastAPI/React pages
- Add auth and deployment profiles for real multi-user environments

---

<div align="center">

If this project helped you or taught you something, a ⭐ makes it easier for others to find. Thanks for reading!

</div>
