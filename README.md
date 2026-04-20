# Medical Agentic Assistant

LangGraph-powered medical consultation and appointment assistant with:

- medical RAG over guideline-style documents
- multi-turn memory and stateful dialogue recovery
- department recommendation and booking / cancellation workflows
- semi-controlled appointment execution (`preview -> explicit confirm -> execute`)
- hybrid retrieval, answer grounding, and low-evidence safety fallback

> Note: the public UI is still evolving. The repository home page intentionally focuses on architecture, workflow, and benchmark notes instead of outdated UI recordings.

## At a Glance

- **Workflow-aware assistant**
  - not just question answering, but also booking, cancellation, clarification recovery, and interruption-safe state transitions
- **Production-style architecture**
  - LangGraph routing, Redis-backed session memory, PostgreSQL / pgvector storage, and explicit workflow safety controls
- **Measured improvements**
  - retrieval and memory benchmarks are included in-repo instead of relying only on qualitative examples

## Why This Repo Exists

Most open-source RAG demos stop at "upload a document and ask questions." This project goes one layer deeper:

- combines **medical Q&A** and **workflow execution** in one conversation system
- keeps **dialogue state** across interruptions, clarifications, and pending confirmations
- treats booking and cancellation as **safe, stateful skills** instead of free-form agent actions
- includes **benchmark and regression tooling** for routing, retrieval, memory, and answer quality

This makes it closer to a real assistant product than a single-path chatbot demo.

## Tech Stack

- **Orchestration**: LangGraph, LangChain
- **LLM / embeddings**: OpenAI-compatible providers, DeepSeek, Ollama-compatible setups
- **Storage**: PostgreSQL, pgvector, Redis
- **UI**: Gradio
- **Evaluation**: in-repo benchmark and regression scripts under `project/benchmarks/`

## Core Capabilities

- **Unified intent routing**
  - rule-first plus LLM fallback routing for `medical_rag`, `triage`, `appointment`, `cancel_appointment`, and clarification recovery
- **Hybrid memory**
  - Redis short-term context, LLM conversation summary, and persisted structured session state
- **Medical retrieval pipeline**
  - parent-child chunking, dense+sparse hybrid retrieval, query rewrite, RRF fusion, rerank, and grounding checks
- **Appointment skill**
  - department / doctor / availability discovery, booking preview, cancellation preview, and explicit confirmation before execution
- **Safety fallback**
  - when KB evidence is weak, the assistant can still provide a conservative general medical answer with a clear disclaimer

## Architecture Snapshot

```text
User -> ChatInterface -> LangGraph Router
                     -> medical_rag -> rewrite -> retrieve -> grounded answer
                     -> triage -> department recommendation
                     -> appointment skill -> discovery / planning / confirm
                     -> cancel skill -> target resolution / preview / confirm
```

Key backend areas:

- `project/core/`
  - system bootstrap, chat interface, document ingestion, observability
- `project/rag_agent/`
  - LangGraph nodes, routing logic, prompts, schemas, retrieval tools
- `project/services/appointment_skill/`
  - booking discovery, planning, and controlled execution
- `project/db/`
  - PostgreSQL / pgvector storage, retrieval logs, route logs, schema helpers
- `project/benchmarks/`
  - benchmark and evaluation entrypoints

## What Makes This Different From a Typical RAG Demo

- it supports **stateful business actions**, not only retrieval
- it keeps **pending confirmations** and resumes them after unrelated turns
- it separates **discovery**, **planning**, and **execution** for appointment workflows
- it includes **low-evidence fallback behavior** instead of only "no answer" responses
- it ships with **benchmark scripts and regression tests** for more than just chat happy paths

## Benchmark Snapshot

Current internal benchmark snapshots in this repo:

- **Prompt token reduction**
  - hybrid memory reduced long-dialogue prompt tokens by **27.4% at P95**
- **Retrieval precision**
  - on the bundled NHC/WHO benchmark setup, **Precision@5 improved from 0.68 to 0.83**

Related scripts:

- `project/benchmarks/evaluate_memory_token_benchmark.py`
- `project/benchmarks/evaluate_medical_rag_benchmark.py`
- `project/benchmarks/evaluate_offline_answer_benchmark.py`
- `project/benchmarks/evaluate_acceptance_report.py`

## Typical Conversation Behaviors

### Medical QA with retrieval

```text
User: 高血压应该注意什么？
Assistant: 先结合知识库证据给出生活方式、监测和就医建议，并附来源信息。
```

### Appointment preview and confirmation

```text
User: 我要挂呼吸内科张医生明天下午的号
Assistant: 先生成预约预览，并要求用户明确回复“确认预约”
User: 确认预约
Assistant: 再执行实际预约写入
```

### Interruption recovery

```text
User: 我要挂呼吸内科张医生明天下午的号
Assistant: 生成预约预览
User: 对了，咳嗽三天了需要拍片吗？
Assistant: 先回答医学问题，同时保留待确认预约状态
User: 确认预约
Assistant: 恢复之前的预约并执行
```

## Quick Start

### 1. Create a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Prepare environment variables

```powershell
Copy-Item project\.env.example project\.env
```

Fill in at least:

- model provider credentials
- PostgreSQL connection settings
- Redis connection settings

### 3. Start required services

You will typically need:

- **PostgreSQL** with pgvector support
- **Redis**
- one configured LLM / embedding provider

### 4. Launch the app

```powershell
.\venv\Scripts\python.exe project\app.py
```

Then open:

- [http://localhost:7860](http://localhost:7860)

## Data and Knowledge Base Notes

This repo does **not** commit local runtime knowledge-base artifacts such as:

- `markdown_docs/`
- `parent_store/`
- `qdrant_db/`
- `runtime/`

Those are treated as disposable local state.

Medical source import helpers and manifests live under:

- `project/import_medical_sources.py`
- `project/core/medical_source_ingest.py`
- `project/core/manifests/`

Additional notes:

- [Medical Import Guide](docs/MEDICAL_IMPORT.md)
- [Medical Sources Guide](docs/MEDICAL_SOURCES.md)

## Testing

Basic validation:

```powershell
.\venv\Scripts\python.exe -m compileall project tests
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Example benchmark runs:

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_memory_token_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_medical_rag_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_acceptance_report.py --json
```

## Safety and Scope

This project is an **engineering demo for medical information assistance and workflow orchestration**.

It is **not** a medical device and does **not** replace licensed clinicians or in-person diagnosis.

The assistant is designed to:

- prioritize safer wording for high-risk symptoms
- require explicit confirmation before appointment writes
- provide disclaimer-backed fallback answers when knowledge-base evidence is weak

## Roadmap

- better public demo data and setup automation
- stronger answer-level evaluation coverage
- more polished UI for public-facing demos
- deeper skill modularization for appointment and reschedule flows

## Contributing

If you want to contribute, start here:

- [CONTRIBUTING.md](CONTRIBUTING.md)

For more implementation detail, see:

- [project/README.md](project/README.md)
