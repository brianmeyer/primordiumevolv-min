import os
import sqlite3
import time
import pickle
from typing import List, Dict, Optional
from app.embeddings import get_model as _get_model
import faiss
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "primordium.db")
CHAT_INDEX_BIN = os.path.join(os.path.dirname(__file__), "..", "storage", ".chat.faiss")
CHAT_INDEX_META = os.path.join(os.path.dirname(__file__), "..", "storage", ".chat.faiss.pkl")
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    # Pragmas for better concurrency/perf on SQLite
    try:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute("PRAGMA temp_store=MEMORY;")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            title TEXT, 
            created_at REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            role TEXT,
            content TEXT,
            created_at REAL,
            param_temp REAL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    try:
        c.execute("ALTER TABLE messages ADD COLUMN param_temp REAL")
    except sqlite3.OperationalError:
        pass
    return c

def create_session(title: str = "New session") -> int:
    c = _conn()
    cursor = c.execute(
        "INSERT INTO sessions(title, created_at) VALUES(?, ?)",
        (title, time.time())
    )
    session_id = cursor.lastrowid
    c.commit()
    c.close()
    return session_id

def list_sessions() -> List[Dict]:
    c = _conn()
    cursor = c.execute("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC")
    sessions = [
        {"id": row[0], "title": row[1], "created_at": row[2]}
        for row in cursor.fetchall()
    ]
    c.close()
    return sessions

def list_messages(session_id: int) -> List[Dict]:
    c = _conn()
    cursor = c.execute(
        "SELECT id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    )
    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3]}
        for row in cursor.fetchall()
    ]
    c.close()
    return messages

def append_message(session_id: int, role: str, content: str) -> int:
    c = _conn()
    cursor = c.execute(
        "INSERT INTO messages(session_id, role, content, created_at) VALUES(?, ?, ?, ?)",
        (session_id, role, content, time.time())
    )
    message_id = cursor.lastrowid
    c.commit()
    c.close()
    
    # Auto-rebuild index if it exists (incremental would be better long-term)
    if os.path.exists(CHAT_INDEX_BIN) and os.path.exists(CHAT_INDEX_META):
        try:
            build_index()  # Rebuild with new message
        except Exception as e:
            print(f"[warn] Auto index rebuild failed: {e}")
    
    return message_id

def append_message_meta(session_id: int, role: str, content: str, param_temp: float | None = None) -> int:
    c = _conn()
    cursor = c.execute(
        "INSERT INTO messages(session_id, role, content, created_at, param_temp) VALUES(?, ?, ?, ?, ?)",
        (session_id, role, content, time.time(), param_temp)
    )
    message_id = cursor.lastrowid
    c.commit()
    c.close()
    return message_id

def get_message(message_id: int) -> Optional[Dict]:
    c = _conn()
    cur = c.execute("SELECT id, session_id, role, content, created_at, param_temp FROM messages WHERE id = ?", (message_id,))
    row = cur.fetchone()
    c.close()
    if not row:
        return None
    return {"id": row[0], "session_id": row[1], "role": row[2], "content": row[3], "created_at": row[4], "param_temp": row[5]}

def build_index():
    """Build vector index from all messages in database"""
    c = _conn()
    cursor = c.execute("SELECT id, session_id, role, content FROM messages")
    messages = cursor.fetchall()
    c.close()
    
    # Ensure storage directory exists
    os.makedirs(os.path.dirname(CHAT_INDEX_BIN), exist_ok=True)
    
    if not messages:
        # Create empty index
        model = _get_model()
        dim = model.get_sentence_embedding_dimension()
        index = faiss.IndexFlatIP(dim)
        faiss.write_index(index, CHAT_INDEX_BIN)
        with open(CHAT_INDEX_META, "wb") as f:
            pickle.dump({"messages": []}, f)
        return
    
    # Prepare content for embedding
    contents = []
    meta_data = []
    
    for msg_id, session_id, role, content in messages:
        if not content or not content.strip():  # Skip empty messages
            continue
        # Combine role and content for better semantic search
        combined_text = f"{role}: {content.strip()}"
        contents.append(combined_text)
        meta_data.append({
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content
        })
    
    if not contents:
        # No valid content to index
        model = _get_model()
        dim = model.get_sentence_embedding_dimension()
        index = faiss.IndexFlatIP(dim)
        faiss.write_index(index, CHAT_INDEX_BIN)
        with open(CHAT_INDEX_META, "wb") as f:
            pickle.dump({"messages": []}, f)
        return
    
    # Generate embeddings
    model = _get_model()
    embeddings = model.encode(contents, convert_to_numpy=True, normalize_embeddings=True)
    
    # Build and save index
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, CHAT_INDEX_BIN)
    
    with open(CHAT_INDEX_META, "wb") as f:
        pickle.dump({"messages": meta_data}, f)
    # Update in-memory cache
    try:
        _refresh_cache()
    except Exception:
        pass

def query_memory(query: str, k: int = 5) -> List[Dict]:
    """Query vector memory for relevant past messages"""
    if not query or not query.strip():
        return []
        
    if not (os.path.exists(CHAT_INDEX_BIN) and os.path.exists(CHAT_INDEX_META)):
        return []
    
    try:
        # Load index and metadata (cached)
        index, meta = _get_cached_index()
        
        messages = meta.get("messages", [])
        if not messages:
            return []
        
        # Generate query embedding
        model = _get_model()
        query_embedding = model.encode([query.strip()], convert_to_numpy=True, normalize_embeddings=True)
        
        # Search
        search_k = min(k, len(messages))
        if search_k <= 0:
            return []
            
        scores, indices = index.search(query_embedding, search_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx >= len(messages) or score < 0.1:  # Filter low similarity
                continue
            
            msg = messages[idx]
            results.append({
                "session_id": msg["session_id"],
                "role": msg["role"],
                "content": msg["content"],
                "score": float(score)
            })
        
        # Sort by score descending
        return sorted(results, key=lambda x: x["score"], reverse=True)
        
    except Exception as e:
        print(f"[warn] Memory query failed: {e}")
        return []

# ---- Simple in-process cache for chat index ----
_cached_index = None
_cached_meta = None
_cached_mtime = (0.0, 0.0)

def _get_mtimes():
    try:
        return (os.path.getmtime(CHAT_INDEX_BIN), os.path.getmtime(CHAT_INDEX_META))
    except Exception:
        return (0.0, 0.0)

def _refresh_cache():
    global _cached_index, _cached_meta, _cached_mtime
    _cached_index = faiss.read_index(CHAT_INDEX_BIN)
    with open(CHAT_INDEX_META, "rb") as f:
        _cached_meta = pickle.load(f)
    _cached_mtime = _get_mtimes()

def _get_cached_index():
    mt = _get_mtimes()
    if _cached_index is None or _cached_meta is None or mt != _cached_mtime:
        _refresh_cache()
    return _cached_index, _cached_meta
