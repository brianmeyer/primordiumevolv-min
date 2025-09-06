"""
Configuration constants for meta-evolution system.
"""
import os

OP_GROUPS = {
    "SEAL": ["change_system", "change_nudge", "raise_temp", "lower_temp", "add_fewshot", "inject_memory", "inject_rag"],
    "WEB": ["toggle_web"],
    "ENGINE": ["use_groq"],
    "SAMPLING": ["raise_top_k", "lower_top_k"],
    "ALPHA": []  # reserved for test_cmd based scoring
}

DEFAULT_OPERATORS = OP_GROUPS["SEAL"] + OP_GROUPS["WEB"] + OP_GROUPS["ENGINE"] + OP_GROUPS["SAMPLING"]

EVO_DEFAULTS = {
    "n": int(os.getenv("META_DEFAULT_N", "12")),           # Number of evolution iterations
    "memory_k": 3,                                           # Number of memory results to retrieve
    "rag_k": 3,                                              # Number of RAG results to retrieve
    "eps": float(os.getenv("META_DEFAULT_EPS", "0.3")),     # Epsilon for epsilon-greedy bandit
    "web_k": 3,                                              # Number of web search results
}

# ---- M1 Feature Flags ----
FF_TRAJECTORY_LOG = os.getenv("FF_TRAJECTORY_LOG", "1") == "1"
FF_PROCESS_COST_REWARD = os.getenv("FF_PROCESS_COST_REWARD", "1") == "1"
FF_OPERATOR_MASKS = os.getenv("FF_OPERATOR_MASKS", "1") == "1"
FF_EVAL_GATE = os.getenv("FF_EVAL_GATE", "1") == "1"

# Reward blending (only if FF_PROCESS_COST_REWARD)
REWARD_ALPHA = float(os.getenv("REWARD_ALPHA", "1.0"))  # base score weight
REWARD_BETA_PROCESS = float(os.getenv("REWARD_BETA_PROCESS", "0.2"))  # process improvement weight
REWARD_GAMMA_COST = float(os.getenv("REWARD_GAMMA_COST", "-0.0005"))  # cost time penalty per ms
