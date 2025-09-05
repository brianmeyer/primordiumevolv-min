# PrimordiumEvolv Minimal (Self-Evolving Engine)
Local UI, tools, evolution loop, and **self-evolving meta-system** calling a local Ollama model with validation, rate limiting, semantic scoring, persistent memory, and intelligent prompt optimization.

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
- **Meta-Evolution**: Self-evolving prompt optimization with epsilon-greedy bandit
- **Recipe Storage**: Persist and reuse successful prompt recipes per task class
- **Operator System**: 10+ mutation operators (temperature, systems, RAG injection, etc.)
- **Artifact Generation**: Detailed run logs and iteration data under `runs/`
- **Evolve**: Evolutionary optimization with semantic scoring
- **Web Search**: Tavily API (if key provided) with DDG fallback
- **RAG**: Local vector search with FAISS and sentence-transformers
- **TODO**: Simple task management with SQLite
- **Rate Limiting**: Token bucket per IP (configurable)
- **Error Handling**: Structured JSON error responses

## Groq Integration
- Set `GROQ_API_KEY` and optional `GROQ_MODEL_ID` in `.env`.
- Verify with `GET /api/health/groq`.
- In the UI, use "Force engine" to route Meta Runs to `ollama` or `groq`; or leave on auto and enable the ENGINE framework to allow the `use_groq` operator.
- You can enable "Compare with Groq" to run a single-shot cross-check on the best variant.

## Real-time Meta Runs
- Async start: `POST /api/meta/run_async` returns `{ run_id }` immediately and performs the run in the background.
- Live updates: `GET /api/meta/stream?run_id=<id>` streams Server-Sent Events with iteration, judge, and completion events.
- UI shows a live "Latest Run" table with operator, engine, model, score, and latency per iteration.

## Judge Mode
- Enable "Judge with Groq" in the Meta panel to pairwise-judge the best local variant against a Groq challenger.
- Responses include a `judge` block; the UI also displays a subtle toast and a verdict panel.

## UI Tips
- Tabs: switch between Chat & Tools, Meta, and Dashboard.
- Shortcuts: Ctrl/Cmd+1/2/3 to switch tabs; Ctrl/Cmd+Enter to run Meta; J toggles Judge; C toggles Compare.
- Health badges indicate Ollama and Groq status; use "List Groq Models" to verify Groq access.

## Judge Mode + Groq
- Set `GROQ_API_KEY` in `.env` (leave `GROQ_MODEL_ID` blank to auto-select from `/models`).
- From the UI, click "List Groq Models" to verify availability.
- Check "Judge with Groq" to enable pairwise judging; responses include a `judge` field like:
  `{"judge":{"mode":"pairwise_groq","verdict":{"winner":"A|B|tie","rationale":"..."},"challenger_model":"groq:model"}}`
- Judge does not alter `best_score`; it provides an orthogonal verdict for audit.

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

### Meta-Evolution System
- `POST /api/meta/run` - Trigger self-evolution cycle with bandit optimization

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

## Meta-Evolution System

The self-evolving engine uses epsilon-greedy bandit selection to choose optimal prompt mutations:

```bash
# Trigger meta-evolution for code generation
curl -X POST http://localhost:8000/api/meta/run \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "task_class": "code", 
    "task": "Write a Python function to calculate fibonacci numbers",
    "assertions": ["def fibonacci", "recursive"],
    "n": 12,
    "memory_k": 3,
    "rag_k": 3
  }'
```

### Available Operators
- `change_system` - Switch system prompt (engineer, analyst, optimizer)
- `change_nudge` - Modify output format constraints
- `raise_temp/lower_temp` - Adjust creativity vs consistency
- `inject_rag` - Add document context from RAG
- `inject_memory` - Include conversation history
- `add_fewshot` - Inject domain examples
- `toggle_web` - Enable/disable web search context
- `raise_top_k/lower_top_k` - Modify token sampling

### Generated Artifacts
Each run creates `runs/{timestamp}/`:
- `results.json` - Final metrics and best recipe
- `iteration_XX.json` - Per-iteration operator selection and scoring
- Recipes automatically saved to database for future use

### Recipe Evolution
- Successful recipes (score > baseline + 0.1) saved to `recipes` table
- High-performing recipes (score > baseline + 0.2) auto-approved
- Best recipes reused as base for future mutations
- Operator statistics tracked for bandit optimization
