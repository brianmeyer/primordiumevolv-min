from functools import lru_cache
from sentence_transformers import SentenceTransformer

EMB_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMB_MODEL_ID)

