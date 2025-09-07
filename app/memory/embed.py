"""
Embedding provider for memory system.
Supports multiple embedding models with fallback strategies.
"""
import os
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

_embedding_model = None
_embedder_type = None

def get_embedding(text: str) -> List[float]:
    """
    Get embedding vector for text using configured MEMORY_EMBEDDER.
    Returns normalized embedding vector.
    """
    global _embedding_model, _embedder_type
    
    embedder = os.getenv("MEMORY_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2")
    
    # Initialize model on first use
    if _embedding_model is None:
        _embedding_model, _embedder_type = _initialize_embedder(embedder)
    
    try:
        if _embedder_type == "sentence-transformers":
            embedding = _embedding_model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        elif _embedder_type == "huggingface":
            # Use HuggingFace API
            import requests
            api_token = os.getenv("HUGGING_FACE_API_TOKEN")
            if not api_token:
                raise ValueError("HUGGING_FACE_API_TOKEN required for HuggingFace embedding")
            
            api_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{embedder}"
            headers = {"Authorization": f"Bearer {api_token}"}
            response = requests.post(api_url, headers=headers, json={"inputs": text})
            
            if response.status_code == 200:
                embedding = response.json()
                if isinstance(embedding, list) and len(embedding) > 0:
                    # Handle different response formats
                    if isinstance(embedding[0], list):
                        # Matrix format, take first/mean
                        embedding = np.mean(embedding, axis=0)
                    else:
                        embedding = np.array(embedding)
                    
                    # Normalize
                    embedding = embedding / np.linalg.norm(embedding)
                    return embedding.tolist()
            
            raise Exception(f"HuggingFace API error: {response.status_code} {response.text}")
            
        elif _embedder_type == "openai":
            # TODO: OpenAI embeddings implementation
            raise NotImplementedError("OpenAI embeddings not yet implemented")
        
        else:
            raise ValueError(f"Unknown embedder type: {_embedder_type}")
            
    except Exception as e:
        logger.error(f"Embedding failed for '{text[:50]}...': {e}")
        # Return fallback zero vector
        return [0.0] * get_embedding_dimension()

def get_embedding_dimension() -> int:
    """Get dimension of embeddings from current embedder."""
    embedder = os.getenv("MEMORY_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2")
    
    if "all-MiniLM-L6-v2" in embedder:
        return 384
    elif "text-embedding-3-small" in embedder:
        return 1536
    elif "text-embedding-3-large" in embedder:
        return 3072
    else:
        # Default fallback
        return 384

def _initialize_embedder(embedder: str):
    """Initialize embedding model based on configuration."""
    try:
        if embedder.startswith("sentence-transformers/"):
            # Try to use local sentence-transformers
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(embedder)
                logger.info(f"Initialized local sentence-transformers model: {embedder}")
                return model, "sentence-transformers"
            except ImportError:
                logger.warning("sentence-transformers not available, falling back to HuggingFace API")
                return None, "huggingface"
        
        elif embedder.startswith("openai/"):
            # TODO: OpenAI client initialization
            logger.warning("OpenAI embeddings not implemented, using HuggingFace fallback")
            return None, "huggingface"
        
        else:
            # Default to HuggingFace API
            return None, "huggingface"
            
    except Exception as e:
        logger.error(f"Failed to initialize embedder {embedder}: {e}")
        raise RuntimeError(f"No embedding provider available. Install sentence-transformers or configure HUGGING_FACE_API_TOKEN")

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    try:
        a = np.array(vec1)
        b = np.array(vec2)
        
        # Handle zero vectors
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(np.dot(a, b) / (norm_a * norm_b))
    except Exception as e:
        logger.error(f"Cosine similarity calculation failed: {e}")
        return 0.0

def estimate_tokens(text: str) -> int:
    """Rough token count estimation (4 chars per token average)."""
    return max(1, len(text) // 4)