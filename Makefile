run:
	uvicorn app.main:app --reload --port ${PORT:-8000}
ingest:
	python -c "from app.tools.rag import build_or_update_index; build_or_update_index('data')"