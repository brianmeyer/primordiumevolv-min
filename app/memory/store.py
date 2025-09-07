"""
Memory store for episodic learning experiences.
Handles storage, retrieval, and maintenance of evolution experiences.
"""
import os
import sqlite3
import json
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
import logging
import math

from app.config import (
    MEMORY_REWARD_FLOOR, MEMORY_MIN_CONFIDENCE, MEMORY_BASELINE_REWARD,
    MEMORY_STORE_MAX_SIZE, MEMORY_TASK_CLASS_FUZZY, MEMORY_REWARD_WEIGHT,
    MEMORY_TIME_DECAY, MEMORY_DECAY_DAYS, MEMORY_POLLUTION_GUARD
)
from app.memory.embed import get_embedding, cosine_similarity, get_embedding_dimension

logger = logging.getLogger(__name__)

@dataclass
class Experience:
    """Individual learning experience with all metadata."""
    id: str
    task_class: str
    task_class_norm: str
    input_hash: str
    input_text: str
    plan_json: Dict[Any, Any]
    operator_used: str
    output_text: str
    reward: float
    improvement_delta: float
    confidence_score: float
    judge_ai: float
    judge_semantic: float
    tokens_in: int
    tokens_out: int
    latency_ms: int
    embedding: List[float]
    created_at: datetime
    last_used_at: Optional[datetime] = None

    @classmethod
    def create(cls, 
               task_class: str,
               input_text: str, 
               plan_json: Dict[Any, Any],
               operator_used: str,
               output_text: str,
               reward: float,
               confidence_score: float,
               judge_ai: float,
               judge_semantic: float,
               tokens_in: int = 0,
               tokens_out: int = 0,
               latency_ms: int = 0) -> 'Experience':
        """Create new experience with computed fields."""
        
        # Compute derived fields
        exp_id = str(uuid.uuid4())
        input_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]
        task_class_norm = normalize_task_class(task_class)
        improvement_delta = reward - MEMORY_BASELINE_REWARD
        embedding = get_embedding(input_text)
        
        return cls(
            id=exp_id,
            task_class=task_class,
            task_class_norm=task_class_norm,
            input_hash=input_hash,
            input_text=input_text,
            plan_json=plan_json,
            operator_used=operator_used,
            output_text=output_text,
            reward=reward,
            improvement_delta=improvement_delta,
            confidence_score=confidence_score,
            judge_ai=judge_ai,
            judge_semantic=judge_semantic,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            embedding=embedding,
            created_at=datetime.utcnow()
        )

class MemoryStore:
    """Persistent store for evolution experiences."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize memory store with database connection."""
        if db_path is None:
            db_path = os.path.join("storage", "memory.db")
        
        self.db_path = db_path
        self._ensure_schema()
        
    def _ensure_schema(self):
        """Create memory tables if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    task_class TEXT NOT NULL,
                    task_class_norm TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    operator_used TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    reward REAL NOT NULL,
                    improvement_delta REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    judge_ai REAL NOT NULL,
                    judge_semantic REAL NOT NULL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    latency_ms INTEGER DEFAULT 0,
                    embedding_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP
                )
            """)
            
            # Create indexes for efficient queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_class ON experiences(task_class)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_class_norm ON experiences(task_class_norm)")  
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reward ON experiences(reward DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_confidence ON experiences(confidence_score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON experiences(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_input_hash ON experiences(input_hash)")
            
    def add(self, experience: Experience) -> bool:
        """
        Add experience to store with pollution guards.
        Returns True if added, False if skipped.
        """
        try:
            # Apply pollution guards
            if MEMORY_POLLUTION_GUARD:
                if (experience.reward < MEMORY_REWARD_FLOOR or 
                    experience.confidence_score < MEMORY_MIN_CONFIDENCE):
                    logger.debug(f"Skipping low-quality experience: reward={experience.reward:.3f}, confidence={experience.confidence_score:.3f}")
                    return False
                    
                # Check for duplicate by input_hash
                if self._is_duplicate(experience.input_hash):
                    logger.debug(f"Skipping duplicate experience: input_hash={experience.input_hash}")
                    return False
            
            # Apply size limits with LRU eviction
            self._enforce_size_limits(experience.task_class_norm)
            
            # Insert experience
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO experiences (
                        id, task_class, task_class_norm, input_hash, input_text,
                        plan_json, operator_used, output_text, reward, improvement_delta,
                        confidence_score, judge_ai, judge_semantic, tokens_in, tokens_out,
                        latency_ms, embedding_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    experience.id, experience.task_class, experience.task_class_norm,
                    experience.input_hash, experience.input_text, 
                    json.dumps(experience.plan_json), experience.operator_used,
                    experience.output_text, experience.reward, experience.improvement_delta,
                    experience.confidence_score, experience.judge_ai, experience.judge_semantic,
                    experience.tokens_in, experience.tokens_out, experience.latency_ms,
                    json.dumps(experience.embedding), experience.created_at.isoformat()
                ))
                
            logger.info(f"Added experience {experience.id[:8]} (task={experience.task_class}, reward={experience.reward:.3f})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add experience: {e}")
            return False
    
    def search(self, 
               query_embedding: List[float], 
               task_class: str, 
               k: int, 
               reward_floor: float) -> List[Experience]:
        """
        Search for similar experiences using multi-factor scoring.
        """
        try:
            candidates = self._get_candidates(task_class)
            
            if not candidates:
                return []
            
            # Score and rank candidates
            scored_candidates = []
            now = datetime.utcnow()
            
            for exp in candidates:
                if exp.reward < reward_floor:
                    continue
                    
                # Calculate similarity score
                similarity = cosine_similarity(query_embedding, exp.embedding)
                
                # Normalize reward to [0,1]
                reward_norm = max(0, min(1, exp.reward))
                
                # Calculate time decay factor
                age_factor = 1.0
                if MEMORY_TIME_DECAY and exp.created_at:
                    days_old = (now - exp.created_at).days
                    age_factor = math.exp(-days_old / MEMORY_DECAY_DAYS)
                
                # Combined score: similarity + reward + time decay
                final_score = (
                    similarity * (1 - MEMORY_REWARD_WEIGHT) + 
                    reward_norm * MEMORY_REWARD_WEIGHT
                ) * age_factor
                
                scored_candidates.append((final_score, exp))
            
            # Sort by score and return top k
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            results = [exp for score, exp in scored_candidates[:k]]
            
            # Update last_used_at for retrieved experiences
            if results:
                self.touch([exp.id for exp in results])
                
            logger.debug(f"Memory search: {len(results)}/{len(candidates)} matches for task_class={task_class}")
            return results
            
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []
    
    def touch(self, ids: List[str]) -> None:
        """Update last_used_at for experiences."""
        try:
            if not ids:
                return
                
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ','.join('?' * len(ids))
                conn.execute(f"""
                    UPDATE experiences 
                    SET last_used_at = ? 
                    WHERE id IN ({placeholders})
                """, [datetime.utcnow().isoformat()] + ids)
                
        except Exception as e:
            logger.error(f"Failed to touch experiences: {e}")
    
    def count(self) -> int:
        """Get total number of stored experiences."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM experiences")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to count experiences: {e}")
            return 0
    
    def _get_candidates(self, task_class: str) -> List[Experience]:
        """Get candidate experiences for search."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build query based on fuzzy matching setting
                if MEMORY_TASK_CLASS_FUZZY:
                    task_class_norm = normalize_task_class(task_class)
                    cursor = conn.execute("""
                        SELECT * FROM experiences 
                        WHERE task_class = ? OR task_class_norm = ?
                        ORDER BY reward DESC, created_at DESC
                        LIMIT 100
                    """, (task_class, task_class_norm))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM experiences 
                        WHERE task_class = ?
                        ORDER BY reward DESC, created_at DESC
                        LIMIT 100
                    """, (task_class,))
                
                experiences = []
                for row in cursor.fetchall():
                    exp = self._row_to_experience(row)
                    if exp:
                        experiences.append(exp)
                        
                return experiences
                
        except Exception as e:
            logger.error(f"Failed to get candidates: {e}")
            return []
    
    def _row_to_experience(self, row) -> Optional[Experience]:
        """Convert database row to Experience object."""
        try:
            return Experience(
                id=row['id'],
                task_class=row['task_class'],
                task_class_norm=row['task_class_norm'],
                input_hash=row['input_hash'],
                input_text=row['input_text'],
                plan_json=json.loads(row['plan_json']),
                operator_used=row['operator_used'],
                output_text=row['output_text'],
                reward=row['reward'],
                improvement_delta=row['improvement_delta'],
                confidence_score=row['confidence_score'],
                judge_ai=row['judge_ai'],
                judge_semantic=row['judge_semantic'],
                tokens_in=row['tokens_in'],
                tokens_out=row['tokens_out'],
                latency_ms=row['latency_ms'],
                embedding=json.loads(row['embedding_json']),
                created_at=datetime.fromisoformat(row['created_at']),
                last_used_at=datetime.fromisoformat(row['last_used_at']) if row['last_used_at'] else None
            )
        except Exception as e:
            logger.error(f"Failed to convert row to experience: {e}")
            return None
    
    def _is_duplicate(self, input_hash: str) -> bool:
        """Check if experience with input_hash already exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT 1 FROM experiences WHERE input_hash = ?", (input_hash,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            return False
    
    def _enforce_size_limits(self, task_class_norm: str) -> None:
        """Enforce per-task-class size limits with LRU eviction."""
        try:
            max_per_class = MEMORY_STORE_MAX_SIZE // 10  # Allow ~10 task classes
            
            with sqlite3.connect(self.db_path) as conn:
                # Count experiences for this task class
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM experiences WHERE task_class_norm = ?
                """, (task_class_norm,))
                count = cursor.fetchone()[0]
                
                if count >= max_per_class:
                    # Remove oldest experiences (LRU)
                    to_remove = count - max_per_class + 1
                    conn.execute("""
                        DELETE FROM experiences 
                        WHERE task_class_norm = ? 
                        AND id IN (
                            SELECT id FROM experiences 
                            WHERE task_class_norm = ?
                            ORDER BY COALESCE(last_used_at, created_at) ASC 
                            LIMIT ?
                        )
                    """, (task_class_norm, task_class_norm, to_remove))
                    
                    logger.info(f"Evicted {to_remove} old experiences for task_class_norm={task_class_norm}")
                    
        except Exception as e:
            logger.error(f"Size limit enforcement failed: {e}")

def normalize_task_class(task_class: str) -> str:
    """Normalize task class for fuzzy matching."""
    if not task_class:
        return ""
        
    # Basic normalization: lowercase, strip, handle synonyms
    normalized = task_class.lower().strip()
    
    # Handle common synonyms
    synonyms = {
        "coding": "code",
        "programming": "code", 
        "writing": "write",
        "analysis": "analyze",
        "research": "analyze",
        "business": "strategy"
    }
    
    return synonyms.get(normalized, normalized)

# Global instance (lazy initialization)
_memory_store = None

def get_memory_store() -> MemoryStore:
    """Get global memory store instance."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store