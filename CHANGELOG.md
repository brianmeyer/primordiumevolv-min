# Changelog

## [2.6.0] - 2025-09-06 - Advanced Two-Judge AI Scoring System

### 🧠 Revolutionary AI Evaluation Architecture
- **Two-Judge System**: Independent evaluation by two different Groq models for robust scoring
- **Automatic Tie-Breaker**: When judges disagree significantly (≥0.3), third judge reviews both evaluations and makes final decision
- **Smart Model Rotation**: Intelligent distribution across 10 cutting-edge models with usage tracking for fairness
- **90/10 AI/Semantic Weighting**: Heavily favor AI judgment over topical similarity for accuracy assessment

### 🎯 Model Pool Excellence
**10 State-of-the-Art Models** with specialized capabilities:
- `llama-3.3-70b-versatile` - Advanced reasoning and analysis
- `openai/gpt-oss-120b` - Large-scale language understanding
- `openai/gpt-oss-20b` - Efficient high-quality evaluation  
- `llama-3.1-8b-instant` - Fast, reliable scoring
- `groq/compound` - Multi-faceted comprehensive analysis
- `groq/compound-mini` - Lightweight efficient evaluation
- `meta-llama/llama-4-maverick-17b-128e-instruct` - Latest instruction-following
- `meta-llama/llama-4-scout-17b-16e-instruct` - Exploration-focused evaluation
- `qwen/qwen3-32b` - Advanced multilingual capabilities
- `moonshotai/kimi-k2-instruct` - Specialized instruction understanding

### 🔬 Technical Implementation
- **Weighted Model Selection**: Inverse frequency weighting ensures even distribution across all models
- **Disagreement Detection**: Automatically triggers tie-breaker when initial judges differ by 30%+
- **Comprehensive Metadata**: Full evaluation breakdown with individual judge scores, reasoning, and decisions
- **Graceful Fallbacks**: Robust error handling with semantic similarity backup when AI judges unavailable
- **Transparent Process**: Detailed logging of which models were used, their individual scores, and final decision rationale

### 📊 Evaluation Criteria
**AI Judges Score On:**
- **Accuracy & Correctness**: Factual accuracy and logical reasoning
- **Completeness & Thoroughness**: Coverage of all task requirements
- **Clarity & Coherence**: Communication effectiveness and structure
- **Relevance to Task**: Alignment with specific requirements
- **Practical Usefulness**: Real-world applicability and value

### 🛠 Integration Benefits
- **Enhanced Outcome Rewards**: More accurate quality assessment leads to better evolution guidance
- **Reduced Noise**: Two-judge consensus eliminates outlier evaluations
- **Better UCB Bandit Performance**: More reliable scores improve operator selection accuracy  
- **Detailed Analytics**: Rich metadata enables deeper analysis of what makes responses high-quality

### ⚙️ Configuration
- **Disagreement Threshold**: 0.3 (configurable) triggers tie-breaker evaluation
- **Weighting**: 90% AI judgment, 10% semantic similarity (optimized through testing)
- **Model Selection**: 2-3 models per evaluation with intelligent rotation
- **Fallback Strategy**: Graceful degradation to semantic-only scoring if needed

---

## [2.5.0] - 2025-09-06 - Human-in-the-Loop Rating Enablement

### ✅ What’s New
- SSE iteration events now include `variant_id` and `output` preview to power the rating panel.
- Added endpoint `GET /api/meta/variants/{variant_id}` to fetch full model outputs for review.
- Rating API stabilized: `POST /api/meta/rate` accepts `{ variant_id, human_score (0–1), feedback }` and stores 1–10 scores.
- UI Quick Test fixes: reads `response` field for chat; session auto‑creation ensures valid `session_id`.
- Advanced settings wired: strategy selector (UCB1 vs epsilon‑greedy), RAG‑K control; iteration max aligned to 24.

### Impact
- Human rating is functional during evolution; submissions are persisted and associated to exact variants.
- Users can inspect the actual outputs generated via the new variant endpoint.
- Advanced settings are now effective and reflected in backend behavior.

### Notes
- Stream chat in the UI parses `{ "token": "..." }` chunks; optional to stop on `{ "done": true }`.
- ε slider is meaningful when `epsilon_greedy` is selected; UCB1 remains the default.

## [2.4.0] - 2025-09-06 - Enhanced Operator Exploration

### 🎯 Improved Operator Selection & Diversity
- **Increased Exploration**: Raised epsilon from 0.3 to 0.6 for more operator experimentation
- **Forced Initial Exploration**: Ensures every operator gets tried at least once before exploitation begins
- **UCB Algorithm**: Added Upper Confidence Bound as alternative to epsilon-greedy selection
- **Selection Algorithm Choice**: New `bandit_algorithm` parameter supports "epsilon_greedy" or "ucb"

### 🔬 Technical Implementation
- **Enhanced EpsilonGreedy**: Modified to prioritize untried operators first, then apply epsilon-greedy logic
- **New UCB Class**: Implements Upper Confidence Bound with confidence interval calculation
- **Algorithm Flexibility**: Runtime selection between exploration strategies via configuration
- **Improved Coverage**: Systematic exploration ensures all 11 available operators get evaluated

### 📊 Problem Solved
- **Previous Issue**: Only 7 out of 11 operators were being used due to early exploitation
- **Root Cause**: ε=0.3 (30% exploration) led to premature convergence on successful operators
- **Solution Impact**: Now guarantees all operators (change_system, raise_temp, add_fewshot, use_groq, etc.) get tried
- **Verification**: Testing confirms 100% operator coverage with both improved algorithms

### 🎯 **Current Results - Improved Diversity Evidence**
**Recent Runs (Post-Implementation)** show previously unused operators now active:
- **✅ use_groq** - Successfully tried in run #20 (previously never used)
- **✅ add_fewshot** - Now appearing in run #22 (previously rare)
- **✅ raise_temp** - Multiple uses in run #22 (previously avoided)
- **✅ change_system** - Successfully tried in run #22 (previously never used)
- **✅ inject_memory** - Active usage in recent runs

**Before vs After Comparison:**
- **Old Behavior**: Converged quickly on ~3 operators (toggle_web, lower_temp, lower_top_k)
- **New Behavior**: Systematic exploration of all 11 operators with forced initial trials

### ⚙️ Configuration Changes
- **Default Epsilon**: Increased from 0.3 to 0.6 in `.env` and `config.py`
- **New Parameter**: `bandit_algorithm` in `meta_run()` function
- **Backward Compatibility**: Existing calls default to epsilon-greedy behavior
- **Environment Override**: `META_DEFAULT_EPS=0.6` can be customized via environment

---

## [2.3.0] - 2025-09-06 - Long-Term Analytics Dashboard

### 📈 Analytics & Learning Insights
- **Comprehensive Analytics API**: New `/api/meta/analytics` endpoint providing system-wide performance metrics
- **Evolution Progress Tracking**: Shows score progression over time with rolling averages
- **Operator Performance Analysis**: Visual charts of best-performing strategies (lower_temp, lower_top_k leading)
- **Task Type Comparison**: Performance breakdown by task class (code, research, business, etc.)
- **Improvement Trends**: Early vs recent performance comparison showing long-term learning
- **System Statistics**: Total runs, timespan, and overall performance metrics

### 🎨 Interactive Dashboard UI
- **Collapsible Analytics Section**: "📈 Long-Term Analytics & Improvement" in UI
- **Real-time Data Loading**: Click "Load Analytics" button for latest insights
- **Visual Performance Charts**: Progress bars and trend displays for easy interpretation
- **Responsive Grid Layout**: Organized display of metrics, operators, and task performance
- **Error Handling**: Graceful degradation with user feedback

### 🔧 Technical Implementation
- **Infinite Value Handling**: Robust JSON serialization with -inf/inf cleanup
- **Rolling Window Analysis**: 3-run rolling averages for trend smoothing
- **Database Optimization**: Efficient queries with proper filtering and indexing
- **Frontend Integration**: JavaScript functions with global scope registration
- **Performance Metrics**: Average execution times and reward calculations

### 📊 Key Insights Revealed
- **Top Operators**: `lower_temp` (22.96 reward), `lower_top_k` (21.03 reward)
- **Strategy Learning**: System identifies best-performing approaches over time  
- **Task Adaptation**: Performance varies by task type, enabling targeted optimization
- **Continuous Improvement**: Historical data proves system evolution across runs

---

## [2.2.0] - 2025-09-06 - M1 Upgrades (Trajectory, Rewards, Masks, Gating)

### ✨ New (Flagged ON by default)
- Trajectory logging per run: writes `runs/{ts}/trajectory.json` with per‑iteration op/engine/time/score/reward.
- Process + cost reward blending: bandit reward = α·(score−baseline) + β·Δprocess − γ·time_ms (env‑tunable weights).
- Operator masks per task: optional `storage/operator_masks.json` (task_class → framework_mask/operators allowlist).
- Eval suite + gating: safety probes at end of run; writes `runs/{ts}/eval.json` and adds `eval` to results.

### 🛠 Defaults & Wiring
- Meta defaults updated to N=12, ε=0.3 (env overridable).
- SSE event alignment: frontend handles `iter`, `judge`, `done` events from backend.
- Async runs: UI uses `POST /api/meta/run_async` and streams `/api/meta/stream`.
- Stats init fix: `/api/meta/stats` initializes DB schema to avoid early 500s.
- No app‑side token caps for Chat/Meta (models control length).
- Groq picker filters out non‑chat models (tts/whisper/embed).

### ⚙️ Feature Flags (env)
- `FF_TRAJECTORY_LOG`, `FF_PROCESS_COST_REWARD`, `FF_OPERATOR_MASKS`, `FF_EVAL_GATE` (all enabled by default).
- Reward weights: `REWARD_ALPHA`, `REWARD_BETA_PROCESS`, `REWARD_GAMMA_COST`.
- Meta defaults: `META_DEFAULT_N`, `META_DEFAULT_EPS`.

---

## [2.1.0] - 2025-09-06 - Human Rating System

### 🧑‍⚖️ Human-in-the-Loop Feedback
- **Interactive Rating Panel**: Rate AI responses during evolution with 1-10 scale or thumbs up/down
- **Real-time Rating Interface**: Shows after each iteration response for immediate feedback
- **Feedback Collection**: Optional text feedback alongside numerical ratings
- **Database Integration**: All ratings stored in `human_ratings` table with variant linkage
- **API Endpoint**: `/api/meta/rate` for programmatic rating submission
- **Validation**: Proper input validation (1-10 scores, valid variant IDs)

### 🔧 Technical Implementation
- **New Database Table**: `human_ratings(id, variant_id, human_score, feedback, created_at)`
- **Request Model**: `HumanRatingRequest` with validation constraints
- **Store Function**: `save_human_rating()` for persistent storage
- **UI Integration**: Rating panel appears automatically during evolution
- **Error Handling**: Graceful validation and user feedback

### 📱 User Experience
- **Seamless Workflow**: Rating panel appears after each AI response
- **Multiple Rating Methods**: Quick thumbs up/down or detailed 1-10 scale
- **Visual Feedback**: Real-time rating submission status
- **Non-intrusive Design**: Collapsible panel maintains clean interface

---

## [2.0.0] - 2025-09-06 - Human-Centered UI Redesign

### 🎯 Major UI Overhaul
- **Complete interface redesign** using human-centered design principles
- **Single primary action**: Focused "🚀 Start Evolution" workflow
- **Natural language prompts**: "What should the AI get better at?" instead of technical jargon
- **Progressive disclosure**: Advanced settings collapsed by default
- **Task-oriented design**: Dropdown for Code, Analysis, Writing, Business, etc.

### 📊 Real-time Progress & Streaming
- **Visual progress bars** with real-time completion percentages
- **Live step tracking**: "🔄 Iteration 2: Trying toggle_web" status updates
- **Streaming output display**: Watch AI responses as they're generated
- **Connection status**: "📡 Connected to evolution stream" feedback
- **Comprehensive logging**: Debug info in browser console (F12)

### 🎨 Improved User Experience
- **Collapsible sections** for clean interface:
  - 💬 Quick Test Current AI
  - ⚙️ Advanced Evolution Settings
  - 📊 View Evolution History
- **Health monitoring**: Auto-updating Ollama/Groq status badges
- **Error handling**: Clear error messages with recovery suggestions
- **Mobile-friendly**: Responsive design for all devices
- **Glassmorphism theme**: Modern dark UI with backdrop blur effects

### 🔧 Technical Improvements
- **Fixed meta-evolution freezing bug**: Runs now always complete properly
- **Enhanced health endpoints**: Added `/api/health/ollama` endpoint
- **Better error handling**: Graceful degradation with user feedback
- **JavaScript fixes**: Corrected static file paths and loading issues
- **Console debugging**: Detailed logging for troubleshooting

### 🚀 New User Flow
1. Enter task description (natural language)
2. Select task type and number of iterations
3. Click "Start Evolution" button
4. Watch real-time progress with streaming updates
5. View results with improvement metrics and best strategies

### 🛠️ Bug Fixes
- Fixed health badges stuck on "checking..." status
- Resolved JavaScript loading issues (404 errors)
- Fixed meta-evolution runs not completing (`finished_at` null bug)
- **Fixed JavaScript function scope issue**: Resolved "startEvolution is not a function" error by explicitly attaching functions to window object
- **Complete JavaScript functionality restoration**: Added missing `quickTest`, `streamTest`, `loadEvolutionHistory` functions with proper global scope
- Improved streaming connection handling with timeout management
- Enhanced error reporting with detailed stack traces

### 📈 Performance Improvements
- **Streaming progress updates**: Real-time feedback during evolution
- **Connection pooling**: Better resource management for long-running operations
- **Caching improvements**: Faster static file serving
- **Background processing**: Non-blocking evolution runs

---

## [1.x.x] - Previous Versions

### Legacy Features (Still Available)
- Multi-engine support (Ollama + Groq)
- Epsilon-greedy bandit optimization
- Recipe persistence and analytics
- Memory system with FAISS vector search
- RAG integration with document indexing  
- Web search capabilities
- Real-time streaming with Server-Sent Events
- Judge mode for comparative evaluation

### Migration Notes
- All legacy functionality preserved in hidden compatibility layer
- Old API endpoints remain functional
- Previous configurations still work
- Technical users can access advanced features through collapsible sections
