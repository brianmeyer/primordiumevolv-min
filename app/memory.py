import os
import sqlite3
import time
import pickle
from typing import List, Dict
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "primordium.db")
CHAT_INDEX_BIN = ".chat.faiss"
CHAT_INDEX_META = ".chat.faiss.pkl"
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
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
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
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
    return message_id

def build_index():
    """Build vector index from all messages in database"""
    c = _conn()
    cursor = c.execute("SELECT id, session_id, role, content FROM messages")
    messages = cursor.fetchall()
    c.close()
    
    if not messages:
        # Create empty index
        model = SentenceTransformer(EMB_MODEL)
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
        # Combine role and content for better semantic search
        combined_text = f"{role}: {content}"
        contents.append(combined_text)
        meta_data.append({
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content
        })
    
    # Generate embeddings
    model = SentenceTransformer(EMB_MODEL)
    embeddings = model.encode(contents, convert_to_numpy=True, normalize_embeddings=True)
    
    # Build and save index
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, CHAT_INDEX_BIN)
    
    with open(CHAT_INDEX_META, "wb") as f:
        pickle.dump({"messages": meta_data}, f)

def query_memory(query: str, k: int = 5) -> List[Dict]:
    """Query vector memory for relevant past messages"""
    if not (os.path.exists(CHAT_INDEX_BIN) and os.path.exists(CHAT_INDEX_META)):
        return []
    
    # Load index and metadata
    index = faiss.read_index(CHAT_INDEX_BIN)
    with open(CHAT_INDEX_META, "rb") as f:
        meta = pickle.load(f)
    
    messages = meta["messages"]
    if not messages:
        return []
    
    # Generate query embedding
    model = SentenceTransformer(EMB_MODEL)
    query_embedding = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    
    # Search
    scores, indices = index.search(query_embedding, min(k, len(messages)))
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1 or idx >= len(messages):
            continue
        
        msg = messages[idx]
        results.append({
            "session_id": msg["session_id"],
            "role": msg["role"],
            "content": msg["content"],
            "score": float(score)
        })
    
    return results