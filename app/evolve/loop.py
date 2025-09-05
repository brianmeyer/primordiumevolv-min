from typing import List, Dict
from app.ollama_client import generate
from sentence_transformers import SentenceTransformer
import numpy as np

BASE_SYSTEMS = [
    "You are a concise senior engineer. Return precise, directly usable output.",
    "You are a careful analyst. Explain steps briefly and verify constraints.",
    "You are a creative optimizer. Offer improved alternatives and rationale."
]
NUDGES = [
    "Respond in bullet points.",
    "Prioritize correctness and include one test example.",
    "Add a short checklist at the end."
]

_emb = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def _cos(a, b): 
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

def score_output(out: str, assertions: List[str] | None, task: str) -> float:
    # semantic similarity to task
    qv = _emb.encode([task], convert_to_numpy=True, normalize_embeddings=True)[0]
    ov = _emb.encode([out[:1500]], convert_to_numpy=True, normalize_embeddings=True)[0]
    score = 0.5 * _cos(qv, ov)
    
    # assertion coverage semantic
    if assertions:
        av = _emb.encode(assertions, convert_to_numpy=True, normalize_embeddings=True)
        cov = np.mean([_cos(ov, a) for a in av])
        score += 0.5 * cov
    
    return score

def evolve(task: str, assertions: List[str] | None = None, n: int = 5) -> Dict:
    best = {"score": -1.0, "response": "", "recipe": {}}
    tried = 0
    
    for sys in BASE_SYSTEMS:
        if tried >= n:
            break
        for nudge in NUDGES:
            if tried >= n:
                break
            
            prompt = f"{task}\n\nConstraints:\n{nudge}"
            out = generate(prompt, system=sys)
            s = score_output(out, assertions, task)
            
            if s > best["score"]:
                best = {"score": s, "response": out, "recipe": {"system": sys, "nudge": nudge}}
            
            tried += 1
    
    return best