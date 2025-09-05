"""
Configuration constants for meta-evolution system.
"""

DEFAULT_OPERATORS = [
    "change_system",
    "change_nudge", 
    "inject_memory",
    "inject_rag",
    "raise_temp",
    "lower_temp",
    "add_fewshot",
    "toggle_web",
    "raise_top_k",
    "lower_top_k"
]

EVO_DEFAULTS = {
    "n": 12,           # Number of evolution iterations
    "memory_k": 3,     # Number of memory results to retrieve
    "rag_k": 3,        # Number of RAG results to retrieve
    "eps": 0.1,        # Epsilon for epsilon-greedy bandit
    "web_k": 3         # Number of web search results
}