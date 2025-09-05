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

def score_output(out: str, assertions: List[str] | None, task: str, test_cmd: str = None, test_weight: float = 0.0) -> float:
    # semantic similarity to task
    qv = _emb.encode([task], convert_to_numpy=True, normalize_embeddings=True)[0]
    ov = _emb.encode([out[:1500]], convert_to_numpy=True, normalize_embeddings=True)[0]
    score = 0.5 * _cos(qv, ov)
    
    # assertion coverage semantic
    if assertions:
        av = _emb.encode(assertions, convert_to_numpy=True, normalize_embeddings=True)
        cov = np.mean([_cos(ov, a) for a in av])
        score += 0.5 * cov
    
    # external test command scoring
    if test_cmd and test_weight > 0.0:
        try:
            import os
            import subprocess
            
            # Write output to artifacts/out.txt for test to check
            os.makedirs("artifacts", exist_ok=True)
            with open("artifacts/out.txt", "w") as f:
                f.write(out)
            
            # Run test command
            result = subprocess.run(test_cmd, shell=True, capture_output=True, timeout=30)
            test_score = 1.0 if result.returncode == 0 else 0.0
            
            # Blend with semantic score based on test_weight
            score = (1 - test_weight) * score + test_weight * test_score
        except Exception:
            pass  # If test fails, keep original score
    
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

def stitch_context(rag_snips: List[str], mem_snips: List[str], web_snips: List[str], fewshot: str = None) -> str:
    """
    Stitch together different context sources into a coherent context block.
    
    Args:
        rag_snips: List of RAG document snippets
        mem_snips: List of memory/conversation snippets  
        web_snips: List of web search snippets
        fewshot: Optional few-shot example string
        
    Returns:
        Formatted context string
    """
    blocks = []
    
    if fewshot:
        blocks.append(f"Examples:\n{fewshot}")
        
    if rag_snips:
        blocks.append("RAG:\n" + "\n---\n".join(rag_snips))
        
    if mem_snips:
        blocks.append("Memory:\n" + "\n---\n".join(mem_snips))
        
    if web_snips:
        blocks.append("Web:\n" + "\n---\n".join(web_snips))
    
    return "\n\n".join(blocks)