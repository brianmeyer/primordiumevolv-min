"""
Global cache management for preventing shared state issues between server instances.
"""

def clear_all_caches():
    """Clear all application caches for clean startup."""
    try:
        # Clear Ollama client cache
        from app.ollama_client import clear_cache as clear_ollama
        clear_ollama()
    except ImportError:
        pass
    
    try:
        # Clear Groq client cache
        from app.groq_client import clear_cache as clear_groq
        clear_groq()
    except ImportError:
        pass
    
    try:
        # Clear embeddings cache
        from app.embeddings import get_embedder
        get_embedder.cache_clear()
    except (ImportError, AttributeError):
        pass
    
    # Note: New memory system (app.memory.store) uses persistent storage
    # and should NOT be cleared between server restarts
    
    print("✓ All application caches cleared")

def clear_streaming_queues():
    """Clear any streaming queues."""
    try:
        from app.main import streaming_queues
        streaming_queues.clear()
        print("✓ Streaming queues cleared")
    except ImportError:
        pass