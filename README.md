# PrimordiumEvolv Minimal (hardened)
Local UI, tools, and evolution loop calling a local Ollama model with validation, rate limiting, and better scoring.

## Prereqs
- Python 3.11+
- Ollama running with the model pulled:
  - `ollama pull qwen3:4b` (or set MODEL_ID to your local tag)
  - `ollama serve`

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
make ingest   # optional: index files in ./data
make run      # http://localhost:8000
```

## Features
- **Chat**: Direct Ollama model interaction
- **Evolve**: Evolutionary optimization with semantic scoring
- **Web Search**: Tavily API (if key provided) with DDG fallback
- **RAG**: Local vector search with FAISS and sentence-transformers
- **TODO**: Simple task management with SQLite
- **Rate Limiting**: Token bucket per IP (configurable)
- **Error Handling**: Structured JSON error responses

## API Endpoints
- `GET /` - UI interface
- `GET /api/health` - Health check
- `POST /api/chat` - Chat with model
- `POST /api/evolve` - Run evolution loop
- `POST /api/web/search` - Web search
- `POST /api/rag/build` - Build vector index
- `POST /api/rag/query` - Query vector index
- `POST /api/todo/add` - Add todo
- `GET /api/todo/list` - List todos
- `POST /api/todo/complete` - Complete todo
- `POST /api/todo/delete` - Delete todo