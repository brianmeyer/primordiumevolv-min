import os, glob, pickle
from typing import List, Dict
from app.embeddings import get_model as _get_model
import faiss

EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_BIN = os.path.join(os.path.dirname(__file__), "..", "..", "storage", ".faiss")
INDEX_META = os.path.join(os.path.dirname(__file__), "..", "..", "storage", ".faiss.pkl")

# Use shared embedding model loader

def _load_docs(data_dir="data") -> List[Dict]:
    docs = []
    for p in glob.glob(os.path.join(data_dir, "**", "*"), recursive=True):
        if p.lower().endswith((".txt", ".md")):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    docs.append({"path": p, "text": f.read()})
            except Exception:
                continue
        elif p.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                pdf = PdfReader(p)
                text = "\n".join([pg.extract_text() or "" for pg in pdf.pages])
                docs.append({"path": p, "text": text})
            except Exception:
                continue
    return docs

def _chunk(text, size=800, overlap=120):
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i+size])
        i += max(1, size - overlap)
    return out

def build_or_update_index(data_dir="data"):
    docs = _load_docs(data_dir)
    chunks = []
    sources = []
    for d in docs:
        for ch in _chunk(d["text"]):
            if ch.strip():
                chunks.append(ch.strip())
                sources.append(d["path"])
    
    # Ensure storage directory exists
    os.makedirs(os.path.dirname(INDEX_BIN), exist_ok=True)
    
    # always write valid index artifacts
    model = _get_model()
    dim = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatIP(dim)
    
    if chunks:
        embs = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
        index.add(embs)
    
    faiss.write_index(index, INDEX_BIN)
    with open(INDEX_META, "wb") as f: 
        pickle.dump({"sources": sources, "chunks": chunks}, f)

def query(q: str, k: int = 5):
    if not q or not q.strip():
        return []
        
    if not (os.path.exists(INDEX_BIN) and os.path.exists(INDEX_META)):
        return []
    
    try:
        model = _get_model()
        index = faiss.read_index(INDEX_BIN)
        with open(INDEX_META, "rb") as f: 
            meta = pickle.load(f)
        
        chunks = meta.get("chunks", [])
        sources = meta.get("sources", [])
        
        if not chunks:
            return []
        
        qv = model.encode([q.strip()], convert_to_numpy=True, normalize_embeddings=True)
        search_k = min(k, len(chunks))
        D, I = index.search(qv, search_k)
        results = []
        
        for score, idx in zip(D[0], I[0]):
            if idx == -1 or idx >= len(chunks) or score < 0.1:  # Filter low similarity
                continue
            results.append({
                "score": float(score),
                "chunk": chunks[idx],
                "source": sources[idx] if idx < len(sources) else "unknown"
            })
        
        # Sort by score descending
        return sorted(results, key=lambda x: x["score"], reverse=True)
        
    except Exception as e:
        print(f"[warn] RAG query failed: {e}")
        return []
