# PrimordiumEvolv Minimal (hardened)
Local UI, tools, and evolution loop calling a local Ollama model with validation, rate limiting, better scoring, and persistent chat memory.

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
- **Chat**: Direct Ollama model interaction with persistent session memory
- **Memory**: Vector-based semantic search across conversation history
- **Evolve**: Evolutionary optimization with semantic scoring
- **Web Search**: Tavily API (if key provided) with DDG fallback
- **RAG**: Local vector search with FAISS and sentence-transformers
- **TODO**: Simple task management with SQLite
- **Rate Limiting**: Token bucket per IP (configurable)
- **Error Handling**: Structured JSON error responses

## API Endpoints

### Core
- `GET /` - UI interface
- `GET /api/health` - Health check
- `POST /api/chat` - Chat with model (requires session_id)
- `POST /api/evolve` - Run evolution loop

### Session Management
- `POST /api/session/create` - Create new chat session
- `GET /api/session/list` - List all sessions
- `GET /api/session/{id}/messages` - Get messages from session
- `POST /api/session/{id}/append` - Add message to session

### Memory System
- `POST /api/memory/build` - Build vector index from all messages
- `POST /api/memory/query` - Query conversation history semantically

### Tools
- `POST /api/web/search` - Web search
- `POST /api/rag/build` - Build vector index
- `POST /api/rag/query` - Query vector index
- `POST /api/todo/add` - Add todo
- `GET /api/todo/list` - List todos
- `POST /api/todo/complete` - Complete todo
- `POST /api/todo/delete` - Delete todo

## Quick Test

Test the new memory features:

```bash
# Create a session
curl -X POST http://localhost:8000/api/session/create \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Session"}'
# Returns: {"id": 1}

# Add some messages to the session
curl -X POST http://localhost:8000/api/session/1/append \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "I love programming in Python"}'

curl -X POST http://localhost:8000/api/session/1/append \
  -H "Content-Type: application/json" \
  -d '{"role": "assistant", "content": "Python is great for data science and web development!"}'

# Build the memory index
curl -X POST http://localhost:8000/api/memory/build

# Query the memory
curl -X POST http://localhost:8000/api/memory/query \
  -H "Content-Type: application/json" \
  -d '{"q": "programming languages", "k": 5}'

# Chat with memory context
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What did we discuss about Python?", "session_id": 1}'
```