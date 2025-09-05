import os, glob, pickle
from typing import List, Dict
from sentence_transformers import SentenceTransformer
import faiss

EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_BIN = ".faiss"
INDEX_META = ".faiss.pkl"

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
                chunks.append(ch)
                sources.append(d["path"])
    
    # always write valid index artifacts
    model = SentenceTransformer(EMB_MODEL)
    dim = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatIP(dim)
    
    if chunks:
        embs = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
        index.add(embs)
    
    faiss.write_index(index, INDEX_BIN)
    with open(INDEX_META, "wb") as f: 
        pickle.dump({"sources": sources, "chunks": chunks}, f)

def query(q: str, k: int = 5):
    if not (os.path.exists(INDEX_BIN) and os.path.exists(INDEX_META)):
        return []
    
    model = SentenceTransformer(EMB_MODEL)
    index = faiss.read_index(INDEX_BIN)
    with open(INDEX_META, "rb") as f: 
        meta = pickle.load(f)
    
    qv = model.encode([q], convert_to_numpy=True, normalize_embeddings=True)
    D, I = index.search(qv, k)
    results = []
    
    for score, idx in zip(D[0], I[0]):
        if idx == -1 or idx >= len(meta["chunks"]): 
            continue
        results.append({"score": float(score),
                        "chunk": meta["chunks"][idx],
                        "source": meta["sources"][idx]})
    return results