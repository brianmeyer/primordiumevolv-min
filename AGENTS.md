# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI app and core modules.
  - `main.py`: API routes and middleware; serves `app/ui/`.
  - `models.py`: Pydantic request models.
  - `tools/`: Utilities (`rag.py`, `web_search.py`, `todo.py`).
  - `evolve/`, `meta/`: Evolution loop and meta-operators + store.
  - `utils/`, `errors.py`, `config.py`, `middleware.py`.
  - `ui/`: Static frontend (`index.html`, `app.js`).
- `data/`: Source files for RAG ingestion.
- `storage/`: Generated artifacts (SQLite DB, FAISS indices). Do not edit manually.
- `runs/`, `logs/`: Runtime outputs and structured logs.

## Build, Test, and Development Commands
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run API+UI: `make run` (uvicorn with reload on `PORT`, default 8000).
- Build RAG index: `make ingest` (indexes `data/`).
- Health check: `GET /api/health`.
- No tests are present yet; see Testing Guidelines to add them.

## Coding Style & Naming Conventions
- Python ≥ 3.11. Follow PEP 8, 4-space indent, type hints.
- Files/modules: `snake_case.py`; classes: `PascalCase`; functions/vars: `snake_case`.
- Keep FastAPI endpoints in `app/main.py`; request models in `app/models.py`.
- Prefer small, pure functions; handle errors via `app/errors.py` helpers.

## Testing Guidelines
- Prefer `pytest` with `httpx`/`starlette.testclient` for API tests.
- Place tests under `tests/` as `test_*.py`; name endpoints `test_<route>_<case>()`.
- Example: `pytest -q` (once tests are added). Aim for ~80% coverage on core modules (`tools/`, `memory.py`, `meta/`).

## Commit & Pull Request Guidelines
- Commits: short, imperative subject (e.g., "Add persistent chat history").
- Scope one logical change per commit; include brief rationale if non-obvious.
- PRs: clear description, linked issue, steps to reproduce/verify, and screenshots for UI changes.
- Verify `make run` and `make ingest` succeed before requesting review.

## Security & Configuration Tips
- Copy `.env.example` to `.env`. Key vars: `OLLAMA_HOST`, `MODEL_ID`, `PORT`, `RATE_LIMIT_PER_MIN`, `CORS_ALLOW`.
- Ensure Ollama is reachable and the requested model is pulled; see `/api/health`.
- Avoid committing secrets or large generated files from `storage/`.
