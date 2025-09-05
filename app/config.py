"""
Configuration constants for meta-evolution system.
"""

OP_GROUPS = {
    "SEAL": ["change_system", "change_nudge", "raise_temp", "lower_temp", "add_fewshot", "inject_memory", "inject_rag"],
    "WEB": ["toggle_web"],
    "ENGINE": ["use_groq"],
    "SAMPLING": ["raise_top_k", "lower_top_k"],
    "ALPHA": []  # reserved for test_cmd based scoring
}

DEFAULT_OPERATORS = OP_GROUPS["SEAL"] + OP_GROUPS["WEB"] + OP_GROUPS["ENGINE"] + OP_GROUPS["SAMPLING"]

EVO_DEFAULTS = {
    "n": 12,           # Number of evolution iterations
    "memory_k": 3,     # Number of memory results to retrieve
    "rag_k": 3,        # Number of RAG results to retrieve
    "eps": 0.1,        # Epsilon for epsilon-greedy bandit
    "web_k": 3         # Number of web search results
}
