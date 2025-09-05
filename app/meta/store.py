import os
import sqlite3
import time
import json
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "meta.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    return c

def init_db():
    c = _conn()
    
    # Recipes table - stores proven good prompts/systems for task classes
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_class TEXT,
            system TEXT,
            nudge TEXT,
            params_json TEXT,
            created_at REAL,
            avg_score REAL DEFAULT 0,
            uses INTEGER DEFAULT 0,
            approved INTEGER DEFAULT 0
        )
    """)
    
    # Runs table - stores meta-evolution experiments
    c.execute("""
        CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_class TEXT,
            task TEXT,
            assertions_json TEXT,
            started_at REAL,
            finished_at REAL,
            best_variant_id INTEGER,
            best_score REAL,
            operator_names_json TEXT
        )
    """)
    
    # Add operator_names_json column if missing (migration)
    try:
        c.execute("ALTER TABLE runs ADD COLUMN operator_names_json TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Variants table - individual attempts within a run
    c.execute("""
        CREATE TABLE IF NOT EXISTS variants(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            system TEXT,
            nudge TEXT,
            params_json TEXT,
            prompt TEXT,
            output TEXT,
            score REAL,
            created_at REAL,
            operator_name TEXT,
            groups_json TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)
    
    # Add analytics columns if missing (migration)
    try:
        c.execute("ALTER TABLE variants ADD COLUMN operator_name TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE variants ADD COLUMN groups_json TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Operator stats table - bandit statistics
    c.execute("""
        CREATE TABLE IF NOT EXISTS operator_stats(
            name TEXT PRIMARY KEY,
            n INTEGER DEFAULT 0,
            avg_reward REAL DEFAULT 0
        )
    """)
    
    c.commit()
    c.close()

def save_run_start(task_class: str, task: str, assertions: Optional[List[str]]) -> int:
    c = _conn()
    assertions_json = json.dumps(assertions) if assertions else None
    cursor = c.execute(
        "INSERT INTO runs(task_class, task, assertions_json, started_at) VALUES(?, ?, ?, ?)",
        (task_class, task, assertions_json, time.time())
    )
    run_id = cursor.lastrowid
    c.commit()
    c.close()
    return run_id

def save_variant(run_id: int, system: str, nudge: str, params: dict, 
                prompt: str, output: str, score: float, 
                operator_name: str = None, groups_json: str = None) -> int:
    c = _conn()
    cursor = c.execute(
        "INSERT INTO variants(run_id, system, nudge, params_json, prompt, output, score, created_at, operator_name, groups_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, system, nudge, json.dumps(params), prompt, output, score, time.time(), operator_name, groups_json)
    )
    variant_id = cursor.lastrowid
    c.commit()
    c.close()
    return variant_id

def save_run_finish(run_id: int, best_variant_id: int, best_score: float, operator_names: List[str] = None):
    c = _conn()
    operator_names_json = json.dumps(operator_names) if operator_names else None
    c.execute(
        "UPDATE runs SET finished_at = ?, best_variant_id = ?, best_score = ?, operator_names_json = ? WHERE id = ?",
        (time.time(), best_variant_id, best_score, operator_names_json, run_id)
    )
    c.commit()
    c.close()

def upsert_operator_stat(name: str, reward: float):
    c = _conn()
    # Get current stats
    cursor = c.execute("SELECT n, avg_reward FROM operator_stats WHERE name = ?", (name,))
    row = cursor.fetchone()
    
    if row:
        n, avg_reward = row
        new_n = n + 1
        new_avg = ((avg_reward * n) + reward) / new_n
        c.execute(
            "UPDATE operator_stats SET n = ?, avg_reward = ? WHERE name = ?",
            (new_n, new_avg, name)
        )
    else:
        c.execute(
            "INSERT INTO operator_stats(name, n, avg_reward) VALUES(?, 1, ?)",
            (name, reward)
        )
    
    c.commit()
    c.close()

def top_recipes(task_class: str, limit: int = 5) -> List[Dict]:
    c = _conn()
    cursor = c.execute(
        "SELECT id, system, nudge, params_json, avg_score, uses FROM recipes WHERE task_class = ? AND approved = 1 ORDER BY avg_score DESC LIMIT ?",
        (task_class, limit)
    )
    recipes = []
    for row in cursor.fetchall():
        recipes.append({
            "id": row[0],
            "system": row[1],
            "nudge": row[2], 
            "params": json.loads(row[3]) if row[3] else {},
            "avg_score": row[4],
            "uses": row[5]
        })
    c.close()
    return recipes

def save_recipe(task_class: str, system: str, nudge: str, params: dict, score: float) -> int:
    c = _conn()
    # Normalize task_class to lowercase and strip spaces
    normalized_task_class = task_class.lower().strip()
    cursor = c.execute(
        "INSERT INTO recipes(task_class, system, nudge, params_json, created_at, avg_score, uses) VALUES(?, ?, ?, ?, ?, ?, 0)",
        (normalized_task_class, system, nudge, json.dumps(params), time.time(), score)
    )
    recipe_id = cursor.lastrowid
    c.commit()
    c.close()
    return recipe_id

def approve_recipe(recipe_id: int, approved: int = 1):
    c = _conn()
    c.execute("UPDATE recipes SET approved = ? WHERE id = ?", (approved, recipe_id))
    c.commit()
    c.close()

def list_operator_stats() -> Dict[str, Dict]:
    c = _conn()
    cursor = c.execute("SELECT name, n, avg_reward FROM operator_stats")
    stats = {}
    for row in cursor.fetchall():
        stats[row[0]] = {"n": row[1], "avg_reward": row[2]}
    c.close()
    return stats

def increment_recipe_usage(recipe_id: int):
    c = _conn()
    c.execute("UPDATE recipes SET uses = uses + 1 WHERE id = ?", (recipe_id,))
    c.commit()
    c.close()

def recent_runs(task_class: str = None, limit: int = 30) -> List[Dict]:
    c = _conn()
    if task_class:
        task_class = task_class.lower().strip()
        cursor = c.execute(
            "SELECT id, task_class, started_at, finished_at, best_score FROM runs WHERE task_class = ? ORDER BY started_at DESC LIMIT ?",
            (task_class, limit)
        )
    else:
        cursor = c.execute(
            "SELECT id, task_class, started_at, finished_at, best_score FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,)
        )
    
    runs = []
    for row in cursor.fetchall():
        runs.append({
            "id": row[0],
            "task_class": row[1],
            "started_at": row[2],
            "finished_at": row[3],
            "best_score": row[4],
            "ts": row[3] or row[2]  # Use finished_at if available, else started_at for trend charts
        })
    c.close()
    return runs

def operator_time_series(limit: int = 200) -> List[Dict]:
    c = _conn()
    cursor = c.execute("SELECT name, n, avg_reward FROM operator_stats ORDER BY name")
    stats = []
    for row in cursor.fetchall():
        stats.append({
            "name": row[0],
            "n": row[1],
            "avg_reward": row[2]
        })
    c.close()
    return stats

def recipes_by_class(task_class: str, limit: int = 10) -> List[Dict]:
    c = _conn()
    normalized_task_class = task_class.lower().strip() if task_class else ""
    if normalized_task_class:
        cursor = c.execute(
            "SELECT id, system, nudge, avg_score, uses, approved FROM recipes WHERE task_class = ? ORDER BY avg_score DESC LIMIT ?",
            (normalized_task_class, limit)
        )
    else:
        cursor = c.execute(
            "SELECT id, system, nudge, avg_score, uses, approved FROM recipes ORDER BY avg_score DESC LIMIT ?",
            (limit,)
        )
    
    recipes = []
    for row in cursor.fetchall():
        recipes.append({
            "id": row[0],
            "system": row[1][:100] + "..." if len(row[1]) > 100 else row[1],  # Truncate for display
            "nudge": row[2],
            "avg_score": row[3],
            "uses": row[4],
            "approved": bool(row[5])
        })
    c.close()
    return recipes