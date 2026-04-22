# Contributing

Thanks for your interest in contributing.

This project mixes:

- LangGraph-based dialogue orchestration
- medical retrieval and answer grounding
- appointment workflow skills
- PostgreSQL / Redis-backed state and logs

Please keep changes focused and easy to review.

## Local Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item project\.env.example project\.env
```

Configure:

- one LLM provider
- PostgreSQL
- Redis

## Development Guidelines

- keep business logic out of the UI layer when possible
- prefer adding or updating tests for routing, state, retrieval, or appointment flow changes
- do not commit secrets, `.env` files, or local vector / runtime artifacts
- keep prompts, schemas, and routing logic aligned when changing workflow behavior

## Validation

Run at minimum:

```powershell
.\venv\Scripts\python.exe -m compileall project tests
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

If you modify benchmark logic, also run the relevant scripts under:

- `project/benchmarks/`

## High-Impact Areas

If you are new to the codebase, the most important directories are:

- `project/rag_agent/`
- `project/core/`
- `project/services/appointment_skill/`
- `project/db/`

## Pull Request Notes

Good PRs usually include:

- a short problem statement
- a behavior summary
- notes on any state / schema / prompt changes
- the validation commands you ran

