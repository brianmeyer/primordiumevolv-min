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
- Chat + Stream Chat: With session memory; optional live token streaming.
- Memory: FAISS vector search over conversations (cached in‑process for speed).
- Meta‑Evolution: UCB1 bandit with advanced total_reward system (outcome + process - cost) featuring two-judge AI evaluation with tie-breaker over operators (system, nudge, temp, memory, RAG, web, engine).
- Recipes + Analytics: Persists best recipes; operator stats tracked over time with reward breakdown.
- RAG: Local vector search (FAISS + sentence‑transformers) over files in `data/`.
- Web Search: Tavily (if key) with DDG fallback.
- **Advanced AI Scoring**: Two-judge evaluation system with 10 rotating Groq models, automatic tie-breaker for disagreements, and 90/10 AI/semantic weighting for robust quality assessment.
- Realtime: Async runs + SSE live updates; inspect full variant output.
- Adaptive Chat: Simple thumbs‑based learning for temperature (opt‑in via buttons).
- Hardened: GZip, structured errors, rate‑limit exemptions for streams.

## Advanced AI Scoring System

The system now features a sophisticated two-judge evaluation system for robust quality assessment:

### **Two-Judge + Tie-Breaker Architecture**
- **Initial Evaluation**: Two different Groq models independently score each response
- **Disagreement Detection**: If judges differ by ≥0.3 points, automatic tie-breaker is triggered
- **Final Decision**: Third judge reviews both evaluations and makes definitive judgment

### **Model Pool & Rotation**
Ten cutting-edge models with intelligent rotation for fair distribution:
- `llama-3.3-70b-versatile` - Advanced reasoning capabilities
- `openai/gpt-oss-120b` - Large-scale language understanding  
- `openai/gpt-oss-20b` - Efficient high-quality evaluation
- `llama-3.1-8b-instant` - Fast, reliable scoring
- `groq/compound` - Multi-faceted analysis
- `groq/compound-mini` - Lightweight evaluation
- `meta-llama/llama-4-maverick-17b-128e-instruct` - Latest instruction-following
- `meta-llama/llama-4-scout-17b-16e-instruct` - Exploration-focused evaluation
- `qwen/qwen3-32b` - Advanced multilingual capabilities
- `moonshotai/kimi-k2-instruct` - Specialized instruction understanding

### **Scoring Methodology**
- **90% AI Judgment**: Evaluates correctness, completeness, clarity, relevance, usefulness
- **10% Semantic Similarity**: Ensures topical alignment with task requirements
- **Robust Fallbacks**: Graceful degradation if AI models unavailable

## System Voices for Generation

Eight distinct system prompts (“voices”) are available for generation; selection is task‑aware and optimized by learning. Enable with `FF_SYSTEMS_V2=1`.

- Engineer (precise executor): “You are a concise senior engineer. Return minimal, directly usable code or config.”
- Analyst (constraint checker): “You are a careful analyst. Trace reasoning in brief steps and confirm assumptions are valid.”
- Optimizer (tradeoff explorer): “You are a creative optimizer. Generate alternatives, compare tradeoffs, and justify the best option.”
- Specialist (accuracy enforcer): “You are a detail-oriented specialist. Ensure correctness, compliance, and complete coverage of edge cases.”
- Architect (systems thinker): “You are an experienced architect. Design robust, extensible systems with long-term maintainability.”
- Product Strategist: “You are a pragmatic product strategist. Frame solutions in terms of user value, business impact, and constraints.”
- Experimenter: “You are a rapid prototyper. Propose small, low-risk tests to validate ideas quickly.”
- Skeptic: “You are a rigorous skeptic. Stress-test assumptions and highlight potential failures.”

Analytics expose voice usage and mean total_reward/cost per system string.
## Groq Integration
- Set `GROQ_API_KEY` and optional `GROQ_MODEL_ID` in `.env`.
- Verify with `GET /api/health/groq`.
- In the UI, use "Force engine" to route Meta Runs to `ollama` or `groq`; or leave on auto and enable the ENGINE framework to allow the `use_groq` operator.
- You can enable "Compare with Groq" to run a single-shot cross-check on the best variant.

## Real-time Meta Runs
- Async start: `POST /api/meta/run_async` returns `{ run_id }` immediately and performs the run in the background.
- Live updates: `GET /api/meta/stream?run_id=<id>` streams Server-Sent Events with iteration, judge, and completion events.
- UI shows a live "Latest Run" table with operator, engine, model, score, and latency per iteration.

## Generation & Evaluation Policy

- All generation is local via Ollama. The engine is enforced as `engine="ollama"` for meta-evolution.
- Groq is used strictly in the evaluation layer (two-judge + optional tie-breaker) to score outputs.
- Artifacts include judge metadata (per-judge scores, model ids, timing) under the evaluation block.

## M1 Upgrades (Enabled by Default)
- **UCB1 Bandit Algorithm**: Default strategy with warm start and stratified exploration for optimal operator diversity.
- **Advanced Total Reward System**: Three-component reward with sophisticated outcome evaluation:
  - **Outcome Reward**: Two-judge AI evaluation (90%) + semantic similarity (10%) with automatic tie-breaker
  - **Process Reward**: Structured reasoning, code quality, and methodology assessment  
  - **Cost Penalty**: Resource efficiency (time, tokens, tool calls) vs baseline
  - **Promotion Policy**: Δ ≥ 0.05, cost ≤ 0.9×baseline with detailed AI judgment metadata
- **Enhanced Artifacts**: Each run generates `reward_breakdown` with detailed judge evaluations and `bandit_state` snapshots for full transparency.
- Trajectory Logging: Writes `runs/{timestamp}/trajectory.json` with per‑iteration operator, engine, time, score, and total_reward.
- Operator Masks per Task: Optional masks from `storage/operator_masks.json` (keys are task_class), supporting `framework_mask` (e.g., `["SEAL","ENGINE"]`) and `operators` allowlists.
- Eval Suite + Gating: Safety probes run at end of run and write `runs/{timestamp}/eval_report.json`. Results include promotion criteria analysis.
- **Bandit Configuration**: UCB exploration constant `c=2.0`, warm start `min_pulls=1`, stratified exploration enabled.
- Defaults: Meta `n=16` with UCB strategy (override via `BANDIT_STRATEGY`, `UCB_C`, `WARM_START_MIN_PULLS`).

Feature Flags (in `.env`)
- `FF_TRAJECTORY_LOG=1`, `FF_PROCESS_COST_REWARD=1`, `FF_OPERATOR_MASKS=1`, `FF_EVAL_GATE=1` (all ON by default).
- UCB Configuration: `BANDIT_STRATEGY=ucb`, `UCB_C=2.0`, `WARM_START_MIN_PULLS=1`, `STRATIFIED_EXPLORE=true`.
- Reward weights: `REWARD_ALPHA=1.0`, `REWARD_BETA_PROCESS=0.2`, `REWARD_GAMMA_COST=-0.0005`.

## Judge Mode
- Enable "Judge with Groq" in the Meta panel to pairwise-judge the best local variant against a Groq challenger.
- Responses include a `judge` block; the UI also displays a subtle toast and a verdict panel.

## New Human-Centered UI (v2.0)

The interface has been completely redesigned with human-centered design principles:

### 🎯 **Main Evolution Interface**
- **Primary Focus**: Single "🚀 Start Evolution" button with clear call-to-action
- **Natural Language**: "What should the AI get better at?" instead of technical jargon
- **Task-Oriented**: Dropdown for task types (Code, Analysis, Writing, Business, etc.)
- **Progressive Disclosure**: Advanced settings collapsed by default

### 📊 **Real-time Progress**
- **Visual Progress Bar**: Shows evolution completion percentage
- **Live Step Tracking**: "🔄 Iteration 2: Trying toggle_web" with status updates
- **Streaming Output**: Real-time display of current AI output
- **Results Display**: Clear score improvements and strategy summaries

### 🎨 **Collapsible Sections**
- **💬 Quick Test**: Test current AI with immediate responses
- **⚙️ Advanced Settings**: Learning rate, memory context, web research controls
- **📊 Evolution History**: View past runs and performance metrics

### 🔧 **Technical Improvements**
- **Health Monitoring**: Auto-updating Ollama/Groq status badges
- **Debug Logging**: Comprehensive console logging for troubleshooting
- **Error Handling**: Clear error messages with recovery suggestions
- **Mobile-Friendly**: Responsive design for all screen sizes

### 🚀 **Usage Flow**
1. Enter task description (e.g., "Write Python functions with error handling")
2. Select task type and iterations (2-15)
3. Click "🚀 Start Evolution" 
4. Watch real-time progress with step-by-step updates
5. View results with improvement metrics and best strategies

## UI Tips (Legacy)
- Health badges show Ollama and Groq status in real-time
- Open browser dev tools (F12) to see detailed console logs
- All complex controls are hidden in collapsible sections
- Evolution progress shows live streaming updates

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
- `GET /api/chat/stream` - Stream Chat (SSE)
- `POST /api/chat/feedback` - Thumbs feedback to adapt chat temperature
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
- `POST /api/meta/run_async` - Start run in background (returns `run_id`)
- `GET /api/meta/stream?run_id=ID` - Live SSE updates (iter/judge/done)
- `GET /api/meta/runs/{run_id}` - Run details + variants
- `GET /api/meta/variants/{variant_id}` - Full output for a specific variant

### Human-in-the-Loop Rating
- UI shows a rating panel during iterations when a response is received.
- SSE `iter` events now include `variant_id` and `output` (preview) to enable rating.
- API: `POST /api/meta/rate`
  - Request: `{ "variant_id": number, "human_score": number (0.0–1.0), "feedback": string? }`
  - Behavior: server stores 1–10 scores in `human_ratings` linked to the variant.
  - Use `GET /api/meta/variants/{variant_id}` to fetch the full response text for review.

Preferences
- ratings_mode: `off | prompted` (default `prompted`). When off, ratings UI is hidden and disabled.
- reading_delay_ms: integer 0–8000 (default 2000). When prompted, delays panel display to allow reading first.
- Preferences are stored in browser localStorage and recorded in run metadata.

### Tools
- `POST /api/web/search` - Web search
- `POST /api/rag/build` - Build vector index
- `POST /api/rag/query` - Query vector index

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

# Stream chat tokens (SSE)
# Frontend parses `data: {"token": "..."}` chunks and stops on `{ "done": true }`

## Golden Set

Deterministic micro-benchmarks to validate changes and measure Δ(total_reward) and costs across six task types.

- Storage: `storage/golden/*.json` — one item per file with schema:
  `{ id, task_type, task_class, task, assertions[], inputs?, expected?, seed, flags{web, rag_k} }`.
- Task types (coverage ≥3–5 items each): Code & Programming, Data Analysis, Creative Writing, Business Strategy, Research & Facts, General Task.

- Endpoints:
  - `GET /api/golden/list` — IDs and metadata.
  - `POST /api/golden/run` — runs all or subset, returns KPI JSON.
- Artifacts: `runs/<ts>/golden_kpis.json` with per‑item and aggregate summary:
  - `per_item`: `{ id, task_type, outcome_reward, process_reward, cost_penalty, total_reward, steps }`
  - `aggregate`: `{ avg_total_reward, avg_cost_penalty, avg_steps, pass_rate }`

## Phase 4: AlphaEvolve‑lite (Criticize → Edit → Test → Decide)

Safe, automated improvement loop on allowlisted files, gated by the Golden Set and unit tests.

- Enable: set `FF_CODE_LOOP=1` (auto‑invokes after each meta run completes) or trigger via the existing Phase‑4 endpoint.
- Modes: `CODE_LOOP_MODE=live|dry_run` (default `live`). Dry‑run produces a plan + KPIs without patching.
- Safety: queue + global lock (at‑most‑one active), idempotency (per `source_run_id`), hard timeout (`CODE_LOOP_TIMEOUT_SECONDS`, default 600s), and rate limit (`CODE_LOOP_MAX_PER_HOUR`, default 3).
- Allowlist + caps: edits limited to reward tuning (via `storage/tuning.json`), `storage/*.json` (Golden Set), and `tests/*`; ≤50 LOC per patch, ≤3 patches per loop; auto‑revert on failure.
- Acceptance gates (ALL must pass):
  - Unit tests pass (`pytest -q`).
  - `Δ(total_reward)_aggregate ≥ PHASE4_DELTA_REWARD_MIN` (default 0.05).
  - `avg_cost_penalty_after ≤ PHASE4_COST_RATIO_MAX × avg_cost_penalty_before` (default 0.9).
  - Artifact schema intact (iteration/trajectory/eval/golden parse and expected fields present).
- Determinism & costs: seeds pinned; `WEB=false`, `rag_k` pinned for Golden runs; model id and RAG index hash logged; evaluation latency is included in `cost_penalty`.
- Artifacts: `runs/<ts>/code_loop.json` with `{ loop_id, source_run_id, mode, critic, patch { unified_diff_snippet, git_commit }, tests, golden_kpis_before_after, thresholds, context, decision }`.

### Configuration (thresholds)

- `PHASE4_DELTA_REWARD_MIN` (float, default `0.05`)
- `PHASE4_COST_RATIO_MAX` (float, default `0.9`)
- `GOLDEN_PASS_RATE_TARGET` (float, default `0.80`)
- `CODE_LOOP_TIMEOUT_SECONDS` (int, default `600`)
- `CODE_LOOP_MAX_PER_HOUR` (int, default `3`)

Thresholds are surfaced in `/api/meta/analytics` and embedded in `code_loop.json`.

## Meta-Evolution System

The self-evolving engine uses UCB1 bandit algorithm with total_reward system to choose optimal prompt mutations:

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
All 11 operators systematically explored via UCB1 algorithm with warm start and stratified exploration:

**SEAL Framework (7 operators):**
- `change_system` - Switch system prompt (engineer, analyst, optimizer) 
- `change_nudge` - Modify output format constraints
- `raise_temp/lower_temp` - Adjust creativity vs consistency
- `inject_rag` - Add document context from RAG  
- `inject_memory` - Include conversation history
- `add_fewshot` - Inject domain examples

**WEB Framework (1 operator):**
- `toggle_web` - Enable/disable web search context

**ENGINE Framework (1 operator):**
- `use_groq` - Switch to Groq API for generation

**SAMPLING Framework (2 operators):**
- `raise_top_k/lower_top_k` - Modify token sampling parameters

**Selection Algorithm (Default: UCB1):**
- `strategy="ucb"` (default) - Upper Confidence Bound with warm start and stratified exploration
- `strategy="epsilon_greedy"` (legacy) - 60% exploration, 40% exploitation

### Generated Artifacts
Each run creates `runs/{timestamp}/`:
- `results.json` - Final metrics with `reward_breakdown` and `bandit_state` snapshots
- `iteration_XX.json` - Per-iteration operator selection with `total_reward` tracking
- `trajectory.json` - Per‑iteration trajectory with reward components (if `FF_TRAJECTORY_LOG=1`)
- `eval_report.json` - Promotion criteria analysis and safety gating (if `FF_EVAL_GATE=1`)
- Recipes automatically saved to database with total_reward-based promotion

### Recipe Evolution
- Successful recipes (Δ(total_reward) ≥ 0.05 AND cost_penalty ≤ 0.9×baseline) saved to `recipes` table
- High-performing recipes (Δ(total_reward) ≥ 0.2 AND cost_penalty ≤ 0.8×baseline) auto-approved
- Best recipes reused as base for future mutations
- UCB bandit statistics tracked with mean_payoff for optimal operator selection

## Current Results (examples)
- Run 7 (briefing): best_score ≈ 0.406 on Ollama; Groq compare ≈ 0.408 (Δ ≈ +0.002). Operator stats favored `toggle_web` (n≈11, avg_reward≈0.451), with `change_nudge` runner‑up.
- Run 9 (briefing): baseline ≈ 0.406 → best_score ≈ 0.413 (Δ ≈ +0.007). Operator stats: `toggle_web` (n≈13, avg_reward≈0.371), `change_nudge` (n≈4, avg_reward≈0.064).

Observations:
- With small N and ε=0.1, the bandit exploited `toggle_web`. To diversify, raise N (8–12), increase ε (0.3–0.5), add domain assertions, and optionally mask out WEB for a run to encourage memory/RAG/system exploration.
- Groq compare showed slight gains on the same prompt/system; enabling the ENGINE mask lets the operator explore engine switches.

## UI Usage (New Evolution Panel)
- Describe task, select Task Type, and click “Start Evolution”. The run starts via `/api/meta/run_async` and streams progress via SSE.
- “Quick Test” sends a one‑off Chat (with memory); “Stream Test” streams the response live.
- Results card shows best score, delta vs baseline, Groq compare, and safety gate status when enabled.

## Troubleshooting
- 500 on `/api/meta/stats`: fixed — the endpoint now initializes the meta DB if needed. If you still see errors, ensure the app has write access to `storage/`.
- Empty trajectory/eval: ensure flags are ON in `.env`; artifacts are written only when enabled.
- Long generation: there is no app‑side token cap; generation length is controlled by the model. Consider force‑engine=groq or using a smaller local model for faster iteration.
