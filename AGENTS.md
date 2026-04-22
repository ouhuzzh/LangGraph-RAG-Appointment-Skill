# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `project/`. Use `project/app.py` as the entrypoint, `project/config.py` for env-driven settings, `project/core/` for orchestration, `project/rag_agent/` for LangGraph nodes and tools, `project/db/` for Qdrant and SQL helpers, `project/memory/` for Redis-backed session state, `project/services/` for domain workflows, and `project/ui/` for the Gradio interface. Reference material lives in `README.md`, `project/README.md`, `docs/`, and `notebooks/`. Runtime data such as `markdown_docs/`, `parent_store/`, and `qdrant_db/` is local state and should not be committed.

## Build, Test, and Development Commands
Set up a local environment with `python -m venv venv` and `venv\Scripts\Activate.ps1`, then install dependencies with `pip install -r requirements.txt`. Copy `project/.env.example` to `project/.env` and fill in provider, Redis, and Postgres settings. Run the app with `python project/app.py`; Gradio serves on `http://localhost:7860`. For containerized runs, use `docker build -t agentic-rag -f project/Dockerfile .` followed by `docker run --name rag-assistant -p 7860:7860 agentic-rag`.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for configuration constants. Keep changes small and module-focused; new RAG flow logic belongs under `project/rag_agent/` or `project/core/`, not in the UI layer. Prefer clear env-backed configuration over hardcoded values, and keep secrets only in `project/.env`.

## Testing Guidelines
There is no committed first-party `tests/` package or pytest config yet, so every change needs a basic smoke test. At minimum run `python -m compileall project` and then launch `python project/app.py` to verify imports, startup, and the affected user flow. If you add automated tests, place them under a new root-level `tests/` package and name files `test_*.py`.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit prefixes such as `feat:` and `fix:`; keep that format and write concise, imperative subjects. PRs should describe behavior changes, note any config or schema updates, and list the commands you ran to verify the change. Include screenshots or short recordings for `project/ui/` edits, and mention any required Redis, Postgres, or model-provider setup.

## Security & Configuration Tips
Do not commit `project/.env`, API keys, or generated vector stores. Treat `markdown_docs/`, `parent_store/`, and `qdrant_db/` as disposable local artifacts unless a task explicitly requires regenerating them.
