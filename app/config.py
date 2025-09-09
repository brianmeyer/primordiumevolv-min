"""
Configuration constants for meta-evolution system.
"""
import os

OP_GROUPS = {
    "SEAL": ["change_system", "change_nudge", "raise_temp", "lower_temp", "add_fewshot", "inject_memory", "inject_rag"],
    "WEB": ["toggle_web"],
    "SAMPLING": ["raise_top_k", "lower_top_k"],
    "ALPHA": []  # reserved for test_cmd based scoring
}

DEFAULT_OPERATORS = OP_GROUPS["SEAL"] + OP_GROUPS["WEB"] + OP_GROUPS["SAMPLING"]

EVO_DEFAULTS = {
    "n": int(os.getenv("META_DEFAULT_N", "16")),                          # Number of evolution iterations
    "memory_k": 3,                                                         # Number of memory results to retrieve
    "rag_k": 3,                                                            # Number of RAG results to retrieve
    "eps": float(os.getenv("META_DEFAULT_EPS", "0.6")),                   # Epsilon for epsilon-greedy bandit (legacy)
    "web_k": 3,                                                            # Number of web search results
    # UCB Bandit Configuration
    "strategy": os.getenv("BANDIT_STRATEGY", "ucb"),                      # "ucb" or "egreedy" 
    "ucb_c": float(os.getenv("UCB_C", "2.0")),                           # UCB exploration constant
    "warm_start_min_pulls": int(os.getenv("WARM_START_MIN_PULLS", "1")),  # Min pulls before UCB
    "stratified_explore": os.getenv("STRATIFIED_EXPLORE", "true").lower() == "true",  # First pass diversity
}

# ---- Active Feature Flags ----
FF_TRAJECTORY_LOG = os.getenv("FF_TRAJECTORY_LOG", "1") == "1"
FF_EVAL_GATE = os.getenv("FF_EVAL_GATE", "1") == "1"
# Auto-run Phase 4 code loop after a meta run finishes
FF_CODE_LOOP = os.getenv("FF_CODE_LOOP", "0") == "1"
CODE_LOOP_MODE = os.getenv("CODE_LOOP_MODE", "live")  # "live" | "dry_run"
CODE_LOOP_TIMEOUT_SECONDS = int(os.getenv("CODE_LOOP_TIMEOUT_SECONDS", "600"))  # 10 minutes default
CODE_LOOP_MAX_PER_HOUR = int(os.getenv("CODE_LOOP_MAX_PER_HOUR", "3"))

# Phase 4 decision thresholds
PHASE4_DELTA_REWARD_MIN = float(os.getenv("PHASE4_DELTA_REWARD_MIN", "0.05"))
PHASE4_COST_RATIO_MAX = float(os.getenv("PHASE4_COST_RATIO_MAX", "0.9"))
GOLDEN_PASS_RATE_TARGET = float(os.getenv("GOLDEN_PASS_RATE_TARGET", "0.8"))

# System voices (generation) feature flag
FF_SYSTEMS_V2 = os.getenv("FF_SYSTEMS_V2", "0") == "1"

# Memory system feature flag and configuration
FF_MEMORY = os.getenv("FF_MEMORY", "0") == "1"
MEMORY_K = int(os.getenv("MEMORY_K", "5"))
MEMORY_REWARD_FLOOR = float(os.getenv("MEMORY_REWARD_FLOOR", "0.6"))
MEMORY_PRIMER_TOKENS_MAX = int(os.getenv("MEMORY_PRIMER_TOKENS_MAX", "800"))
MEMORY_DECAY_DAYS = int(os.getenv("MEMORY_DECAY_DAYS", "30"))
MEMORY_EMBEDDER = os.getenv("MEMORY_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2")
MEMORY_TASK_CLASS_FUZZY = os.getenv("MEMORY_TASK_CLASS_FUZZY", "1") == "1"
MEMORY_REWARD_WEIGHT = float(os.getenv("MEMORY_REWARD_WEIGHT", "0.3"))
MEMORY_TIME_DECAY = os.getenv("MEMORY_TIME_DECAY", "1") == "1"
MEMORY_POLLUTION_GUARD = os.getenv("MEMORY_POLLUTION_GUARD", "1") == "1"
MEMORY_MIN_CONFIDENCE = float(os.getenv("MEMORY_MIN_CONFIDENCE", "0.5"))
MEMORY_BASELINE_REWARD = float(os.getenv("MEMORY_BASELINE_REWARD", "0.5"))
MEMORY_STORE_MAX_SIZE = int(os.getenv("MEMORY_STORE_MAX_SIZE", "50000"))
MEMORY_INJECTION_MODE = os.getenv("MEMORY_INJECTION_MODE", "system_prepend")

# Reward blending configuration (now standard)
REWARD_ALPHA = float(os.getenv("REWARD_ALPHA", "1.0"))  # base score weight
REWARD_BETA_PROCESS = float(os.getenv("REWARD_BETA_PROCESS", "0.2"))  # process improvement weight
REWARD_GAMMA_COST = float(os.getenv("REWARD_GAMMA_COST", "-0.0005"))  # cost time penalty per ms

# Phase 5: Darwin Gödel Machine (DGM) Configuration
FF_DGM = os.getenv("FF_DGM", "0") == "1"                              # Enable DGM system
DGM_PROPOSAL_TIMEOUT = int(os.getenv("DGM_PROPOSAL_TIMEOUT", "300"))   # Proposal timeout in seconds
DGM_CANARY_BATCH_SIZE = int(os.getenv("DGM_CANARY_BATCH_SIZE", "5"))   # Canary test batch size
DGM_COMMIT_THRESHOLD = float(os.getenv("DGM_COMMIT_THRESHOLD", "0.8"))  # Commit threshold for success rate
DGM_ROLLBACK_ENABLED = os.getenv("DGM_ROLLBACK_ENABLED", "1") == "1"   # Enable automatic rollback

# Stage 1: Proposer + Apply dry-run
DGM_USE_JUDGE_POOL = os.getenv("DGM_USE_JUDGE_POOL", "1") == "1"       # Use judge pool for proposals
DGM_PROPOSALS = int(os.getenv("DGM_PROPOSALS", "6"))                    # Number of proposals to generate
DGM_MAX_LOC_DELTA = int(os.getenv("DGM_MAX_LOC_DELTA", "50"))          # Max lines of code delta
DGM_ALLOWED_AREAS = [                                                   # Allowed modification areas
    "prompts", "bandit", "asi_lite", "rag", "memory_policy", "ui_metrics"
]
DGM_LOCAL_MODEL = os.getenv("DGM_LOCAL_MODEL", "llama3.2:3b")          # Fallback local model
DGM_GROQ_MODEL = os.getenv("DGM_GROQ_MODEL", "llama-3.1-8b-instant")  # Fallback Groq model

# Shadow Evaluation Configuration
DGM_CANARY_RUNS = int(os.getenv("DGM_CANARY_RUNS", "25"))               # Golden Set items for shadow eval
DGM_SHADOW_TIMEOUT = int(os.getenv("DGM_SHADOW_TIMEOUT", "300"))        # Shadow eval timeout in seconds
DGM_BASELINE_SAMPLES = int(os.getenv("DGM_BASELINE_SAMPLES", "3"))      # Baseline measurement runs
DGM_MIN_REWARD_DELTA = float(os.getenv("DGM_MIN_REWARD_DELTA", "0.02")) # Minimum meaningful reward delta

# Guard Thresholds for Safety
DGM_FAIL_GUARDS = {
    "error_rate_max": float(os.getenv("DGM_ERROR_RATE_MAX", "0.15")),           # Max 15% error rate
    "latency_p95_regression": float(os.getenv("DGM_LATENCY_REGRESSION_MAX", "500")), # Max 500ms p95 regression
    "reward_delta_min": float(os.getenv("DGM_REWARD_DELTA_MIN", "-0.05"))       # Min reward delta (max 5% regression)
}

# Commit and Rollback Configuration
DGM_ALLOW_COMMITS = os.getenv("DGM_ALLOW_COMMITS", "0") == "1"          # Enable live commits (dangerous!)
DGM_TEST_BEFORE_COMMIT = os.getenv("DGM_TEST_BEFORE_COMMIT", "1") == "1" # Run tests before committing
DGM_PATCH_STORAGE_PATH = os.getenv("DGM_PATCH_STORAGE_PATH", "meta/patches")  # Patch artifact storage

# Import JUDGE_MODELS for DGM proposer
try:
    from app.quality_judge import JUDGE_MODELS as DGM_JUDGE_MODEL_POOL
except ImportError:
    DGM_JUDGE_MODEL_POOL = ["llama-3.1-8b-instant"]  # Fallback if judge not available
