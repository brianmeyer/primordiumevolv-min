import os
import sqlite3
import time
import json
import math
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "meta.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    try:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute("PRAGMA temp_store=MEMORY;")
    except Exception:
        pass
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
            approved INTEGER DEFAULT 0,
            updated_at REAL DEFAULT 0,
            engine TEXT DEFAULT 'ollama',
            engine_confidence REAL DEFAULT 0.5
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
            operator_names_json TEXT,
            meta_version TEXT DEFAULT 'v1',
            config_json TEXT
        )
    """)
    
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
            execution_time_ms INTEGER DEFAULT 0,
            model_id TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)
    
    # Operator stats table - bandit statistics
    c.execute("""
        CREATE TABLE IF NOT EXISTS operator_stats(
            name TEXT PRIMARY KEY,
            n INTEGER DEFAULT 0,
            avg_reward REAL DEFAULT 0,
            total_time_ms INTEGER DEFAULT 0,
            last_used_at REAL DEFAULT 0
        )
    """)

    # Chat temperature stats (adaptive chat parameter)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_temp_stats(
            temp REAL PRIMARY KEY,
            n INTEGER DEFAULT 0,
            avg_reward REAL DEFAULT 0,
            last_used_at REAL DEFAULT 0
        )
    """)
    
    # Engine-specific operator stats
    c.execute("""
        CREATE TABLE IF NOT EXISTS operator_engine_stats(
            operator_name TEXT,
            engine TEXT,
            n INTEGER DEFAULT 0,
            avg_reward REAL DEFAULT 0,
            total_time_ms INTEGER DEFAULT 0,
            last_used_at REAL DEFAULT 0,
            PRIMARY KEY (operator_name, engine)
        )
    """)
    
    # Human ratings table - stores user feedback on variant responses
    c.execute("""
        CREATE TABLE IF NOT EXISTS human_ratings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER,
            human_score INTEGER,
            feedback TEXT,
            created_at REAL,
            FOREIGN KEY (variant_id) REFERENCES variants(id)
        )
    """)
    
    # Migration-safe column additions
    migrations = [
        ("runs", "operator_names_json", "TEXT"),
        ("runs", "meta_version", "TEXT DEFAULT 'v1'"),
        ("runs", "config_json", "TEXT"),
        # New reward system fields for runs
        ("runs", "best_total_reward", "REAL DEFAULT NULL"),
        ("runs", "total_reward_improvement", "REAL DEFAULT NULL"),
        ("variants", "operator_name", "TEXT"),
        ("variants", "groups_json", "TEXT"),
        ("variants", "execution_time_ms", "INTEGER DEFAULT 0"),
        ("variants", "model_id", "TEXT"),
        # New reward system fields for variants
        ("variants", "total_reward", "REAL DEFAULT NULL"),
        ("variants", "outcome_reward", "REAL DEFAULT NULL"),
        ("variants", "process_reward", "REAL DEFAULT NULL"),
        ("variants", "cost_penalty", "REAL DEFAULT NULL"),
        ("variants", "reward_metadata_json", "TEXT DEFAULT NULL"),
        ("recipes", "updated_at", "REAL DEFAULT 0"),
        ("recipes", "engine", "TEXT DEFAULT 'ollama'"),
        ("recipes", "engine_confidence", "REAL DEFAULT 0.5"),
        ("operator_stats", "total_time_ms", "INTEGER DEFAULT 0"),
        ("operator_stats", "last_used_at", "REAL DEFAULT 0"),
        ("chat_temp_stats", "last_used_at", "REAL DEFAULT 0")
    ]
    
    for table, column, column_type in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    
    # Add performance indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_runs_task_class ON runs(task_class)",
        "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_variants_run_id ON variants(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_variants_operator ON variants(operator_name)",
        "CREATE INDEX IF NOT EXISTS idx_variants_score ON variants(score)",
        "CREATE INDEX IF NOT EXISTS idx_recipes_task_class ON recipes(task_class)",
        "CREATE INDEX IF NOT EXISTS idx_recipes_score ON recipes(avg_score)",
        "CREATE INDEX IF NOT EXISTS idx_operator_stats_name ON operator_stats(name)",
        "CREATE INDEX IF NOT EXISTS idx_human_ratings_variant ON human_ratings(variant_id)"
    ]
    
    for idx_sql in indexes:
        try:
            c.execute(idx_sql)
        except sqlite3.OperationalError:
            pass  # Index already exists
    
    # Normalize legacy non-finite values that break JSON encoding
    try:
        # Coerce any -Inf/Inf/NaN textual or non-finite representations to NULL
        for col in ("best_score", "best_total_reward", "total_reward_improvement"):
            try:
                c.execute(f"UPDATE runs SET {col} = NULL WHERE CAST({col} AS TEXT) IN ('-Inf','-inf','Inf','inf','NaN','nan')")
            except Exception:
                pass
        c.commit()
    except Exception:
        # Best-effort; do not fail init
        pass
    
    c.commit()
    c.close()

def get_chat_temp_stats() -> Dict[float, Dict]:
    c = _conn()
    cur = c.execute("SELECT temp, n, avg_reward, last_used_at FROM chat_temp_stats")
    out = {}
    for row in cur.fetchall():
        out[float(row[0])] = {"n": row[1], "avg_reward": row[2], "last_used_at": row[3]}
    c.close()
    return out

def update_chat_temp_stat(temp: float, reward: float):
    c = _conn()
    cur = c.execute("SELECT n, avg_reward FROM chat_temp_stats WHERE temp = ?", (float(temp),))
    row = cur.fetchone()
    now = time.time()
    if row:
        n, avg = row
        new_n = n + 1
        new_avg = ((avg * n) + reward) / new_n
        c.execute("UPDATE chat_temp_stats SET n = ?, avg_reward = ?, last_used_at = ? WHERE temp = ?", (new_n, new_avg, now, float(temp)))
    else:
        c.execute("INSERT INTO chat_temp_stats(temp, n, avg_reward, last_used_at) VALUES(?, 1, ?, ?)", (float(temp), reward, now))
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

def update_run_config(run_id: int, config: dict):
    c = _conn()
    try:
        config_json = json.dumps(config) if config else None
        c.execute("UPDATE runs SET config_json = ? WHERE id = ?", (config_json, run_id))
        c.commit()
    finally:
        c.close()

def save_variant(run_id: int, system: str, nudge: str, params: dict, 
                prompt: str, output: str, score: float, 
                operator_name: str = None, groups_json: str = None,
                execution_time_ms: int = 0, model_id: str = None,
                total_reward: float = None, outcome_reward: float = None,
                process_reward: float = None, cost_penalty: float = None,
                reward_metadata: dict = None) -> int:
    c = _conn()
    reward_metadata_json = json.dumps(reward_metadata) if reward_metadata else None
    cursor = c.execute(
        "INSERT INTO variants(run_id, system, nudge, params_json, prompt, output, score, created_at, operator_name, groups_json, execution_time_ms, model_id, total_reward, outcome_reward, process_reward, cost_penalty, reward_metadata_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, system, nudge, json.dumps(params), prompt, output, score, time.time(), operator_name, groups_json, execution_time_ms, model_id, total_reward, outcome_reward, process_reward, cost_penalty, reward_metadata_json)
    )
    variant_id = cursor.lastrowid
    c.commit()
    c.close()
    return variant_id

def save_run_finish(run_id: int, best_variant_id: int, best_score: float, operator_names: List[str] = None, 
                    best_total_reward: float = None, total_reward_improvement: float = None):
    c = _conn()
    try:
        c.execute("BEGIN TRANSACTION")
        operator_names_json = json.dumps(operator_names) if operator_names else None
        # Sanitize non-finite values to avoid JSON encoding failures downstream
        if isinstance(best_score, float) and (math.isinf(best_score) or math.isnan(best_score)):
            best_score = None
        if isinstance(best_total_reward, float) and (math.isinf(best_total_reward) or math.isnan(best_total_reward)):
            best_total_reward = None
        if isinstance(total_reward_improvement, float) and (math.isinf(total_reward_improvement) or math.isnan(total_reward_improvement)):
            total_reward_improvement = None
        c.execute(
            "UPDATE runs SET finished_at = ?, best_variant_id = ?, best_score = ?, operator_names_json = ?, best_total_reward = ?, total_reward_improvement = ? WHERE id = ?",
            (time.time(), best_variant_id, best_score, operator_names_json, best_total_reward, total_reward_improvement, run_id)
        )
        c.execute("COMMIT")
    except Exception as e:
        c.execute("ROLLBACK")
        raise e
    finally:
        c.close()

def upsert_operator_stat(name: str, reward: float, execution_time_ms: int = 0):
    c = _conn()
    # Get current stats
    cursor = c.execute("SELECT n, avg_reward, total_time_ms FROM operator_stats WHERE name = ?", (name,))
    row = cursor.fetchone()
    
    if row:
        n, avg_reward, total_time_ms = row
        new_n = n + 1
        new_avg = ((avg_reward * n) + reward) / new_n
        new_total_time = total_time_ms + execution_time_ms
        c.execute(
            "UPDATE operator_stats SET n = ?, avg_reward = ?, total_time_ms = ?, last_used_at = ? WHERE name = ?",
            (new_n, new_avg, new_total_time, time.time(), name)
        )
    else:
        c.execute(
            "INSERT INTO operator_stats(name, n, avg_reward, total_time_ms, last_used_at) VALUES(?, 1, ?, ?, ?)",
            (name, reward, execution_time_ms, time.time())
        )
    
    c.commit()
    c.close()

def upsert_operator_engine_stat(operator_name: str, engine: str, reward: float, execution_time_ms: int = 0):
    """Track operator performance by engine for analytics."""
    c = _conn()
    # Get current engine-specific stats
    cursor = c.execute("SELECT n, avg_reward, total_time_ms FROM operator_engine_stats WHERE operator_name = ? AND engine = ?", (operator_name, engine))
    row = cursor.fetchone()
    
    if row:
        n, avg_reward, total_time_ms = row
        new_n = n + 1
        new_avg = ((avg_reward * n) + reward) / new_n
        new_total_time = total_time_ms + execution_time_ms
        c.execute(
            "UPDATE operator_engine_stats SET n = ?, avg_reward = ?, total_time_ms = ?, last_used_at = ? WHERE operator_name = ? AND engine = ?",
            (new_n, new_avg, new_total_time, time.time(), operator_name, engine)
        )
    else:
        c.execute(
            "INSERT INTO operator_engine_stats(operator_name, engine, n, avg_reward, total_time_ms, last_used_at) VALUES(?, ?, 1, ?, ?, ?)",
            (operator_name, engine, reward, execution_time_ms, time.time())
        )
    
    c.commit()
    c.close()

def get_operator_engine_stats() -> Dict[str, Dict[str, Dict]]:
    """Get operator performance stats broken down by engine."""
    c = _conn()
    cursor = c.execute("SELECT operator_name, engine, n, avg_reward, total_time_ms, last_used_at FROM operator_engine_stats")
    stats = {}
    for row in cursor.fetchall():
        op_name, engine, n, avg_reward, total_time_ms, last_used_at = row
        if op_name not in stats:
            stats[op_name] = {}
        stats[op_name][engine] = {
            "n": n,
            "avg_reward": avg_reward, 
            "total_time_ms": total_time_ms,
            "avg_time_ms": total_time_ms / max(1, n),
            "last_used_at": last_used_at
        }
    c.close()
    return stats

def top_recipes(task_class: str, limit: int = 5) -> List[Dict]:
    c = _conn()
    cursor = c.execute(
        "SELECT id, system, nudge, params_json, avg_score, uses, engine, engine_confidence FROM recipes WHERE task_class = ? AND approved = 1 ORDER BY avg_score DESC LIMIT ?",
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
            "uses": row[5],
            "engine": row[6] or "ollama",
            "engine_confidence": row[7] or 0.5
        })
    c.close()
    return recipes

def save_recipe(task_class: str, system: str, nudge: str, params: dict, score: float, engine: str = "ollama", engine_confidence: float = 0.5) -> int:
    c = _conn()
    # Normalize task_class to lowercase and strip spaces
    normalized_task_class = task_class.lower().strip()
    cursor = c.execute(
        "INSERT INTO recipes(task_class, system, nudge, params_json, created_at, avg_score, uses, engine, engine_confidence) VALUES(?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (normalized_task_class, system, nudge, json.dumps(params), time.time(), score, engine, engine_confidence)
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

def save_human_rating(variant_id: int, human_score: int, feedback: str = None) -> int:
    """Save a human rating for a variant response."""
    c = _conn()
    try:
        cursor = c.execute(
            "INSERT INTO human_ratings (variant_id, human_score, feedback, created_at) VALUES (?, ?, ?, ?)",
            (variant_id, human_score, feedback, time.time())
        )
        rating_id = cursor.lastrowid
        c.commit()
        return rating_id
    finally:
        c.close()

def get_analytics_overview() -> Dict:
    """Get comprehensive analytics overview showing system improvement over time."""
    c = _conn()
    try:
        # Basic stats
        cursor = c.execute("""
            SELECT 
                COUNT(*) as total_runs,
                MIN(started_at) as first_run,
                MAX(started_at) as latest_run,
                AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL THEN best_score END) as avg_score
            FROM runs WHERE finished_at IS NOT NULL
        """)
        basic_stats = cursor.fetchone()
        
        # Score progression over time (rolling average)
        cursor = c.execute("""
            SELECT 
                id,
                started_at,
                best_score,
                task_class,
                AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL THEN best_score END) 
                OVER (ORDER BY started_at ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as rolling_avg
            FROM runs 
            WHERE finished_at IS NOT NULL 
            ORDER BY started_at
        """)
        score_progression = []
        for row in cursor.fetchall():
            # Clean up score values - filter out infinite values
            score = None
            if row[2] is not None and str(row[2]) != '-Inf' and str(row[2]) != 'inf':
                try:
                    score = float(row[2])
                    if score == float('inf') or score == float('-inf'):
                        score = None
                except (ValueError, TypeError):
                    score = None
            
            rolling_avg = None
            if row[4] is not None:
                try:
                    rolling_avg = float(row[4])
                    if rolling_avg == float('inf') or rolling_avg == float('-inf'):
                        rolling_avg = None
                except (ValueError, TypeError):
                    rolling_avg = None
            
            score_progression.append({
                "run_id": row[0],
                "timestamp": row[1],
                "score": score,
                "task_class": row[3],
                "rolling_avg": rolling_avg
            })
        
        # Top performing operators
        cursor = c.execute("""
            SELECT name, n, avg_reward, total_time_ms, last_used_at
            FROM operator_stats 
            ORDER BY avg_reward DESC 
            LIMIT 10
        """)
        top_operators = []
        for row in cursor.fetchall():
            top_operators.append({
                "name": row[0],
                "uses": row[1],
                "avg_reward": row[2],
                "total_time_ms": row[3],
                "last_used": row[4],
                "avg_time_per_use": row[3] / row[1] if row[1] > 0 else 0
            })
        
        # Task class performance
        cursor = c.execute("""
            SELECT 
                task_class,
                COUNT(*) as runs,
                AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL THEN best_score END) as avg_score,
                MAX(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL THEN best_score END) as best_score
            FROM runs 
            WHERE finished_at IS NOT NULL 
            GROUP BY task_class
            ORDER BY avg_score DESC
        """)
        task_performance = []
        for row in cursor.fetchall():
            task_performance.append({
                "task_class": row[0],
                "runs": row[1],
                "avg_score": row[2],
                "best_score": row[3]
            })
        
        # Recent performance (last 5 runs vs first 5 runs)
        cursor = c.execute("""
            SELECT AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL AND best_score != 'inf' AND best_score > -999999 THEN best_score END) as avg_score
            FROM (
                SELECT best_score FROM runs 
                WHERE finished_at IS NOT NULL 
                ORDER BY started_at 
                LIMIT 5
            )
        """)
        early_avg = cursor.fetchone()[0]
        
        cursor = c.execute("""
            SELECT AVG(CASE WHEN best_score != '-Inf' AND best_score IS NOT NULL AND best_score != 'inf' AND best_score > -999999 THEN best_score END) as avg_score
            FROM (
                SELECT best_score FROM runs 
                WHERE finished_at IS NOT NULL 
                ORDER BY started_at DESC 
                LIMIT 5
            )
        """)
        recent_avg = cursor.fetchone()[0]
        
        # Reward-based analytics (new system)
        cursor = c.execute("""
            SELECT 
                AVG(total_reward) as avg_total_reward,
                AVG(outcome_reward) as avg_outcome_reward,
                AVG(process_reward) as avg_process_reward,
                AVG(cost_penalty) as avg_cost_penalty,
                COUNT(*) as total_variants_with_rewards
            FROM variants 
            WHERE total_reward IS NOT NULL
        """)
        reward_stats = cursor.fetchone()
        
        # Reward progression over runs
        cursor = c.execute("""
            SELECT 
                r.started_at,
                r.best_total_reward,
                r.total_reward_improvement,
                AVG(r.best_total_reward) OVER (ORDER BY r.started_at ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as rolling_avg_reward
            FROM runs r 
            WHERE r.best_total_reward IS NOT NULL 
            ORDER BY r.started_at
        """)
        reward_progression = []
        for row in cursor.fetchall():
            reward_progression.append({
                "timestamp": row[0],
                "best_total_reward": row[1],
                "total_reward_improvement": row[2],
                "rolling_avg_reward": row[3]
            })
        
        # Top operators by total reward (new metric)
        cursor = c.execute("""
            SELECT 
                v.operator_name, 
                AVG(v.total_reward) as avg_total_reward,
                AVG(v.outcome_reward) as avg_outcome_reward,
                COUNT(*) as uses
            FROM variants v 
            WHERE v.total_reward IS NOT NULL AND v.operator_name IS NOT NULL
            GROUP BY v.operator_name 
            ORDER BY avg_total_reward DESC 
            LIMIT 10
        """)
        top_operators_by_reward = []
        for row in cursor.fetchall():
            top_operators_by_reward.append({
                "name": row[0],
                "avg_total_reward": row[1],
                "avg_outcome_reward": row[2],
                "uses": row[3]
            })
        
        return {
            "basic_stats": {
                "total_runs": basic_stats[0],
                "first_run": basic_stats[1],
                "latest_run": basic_stats[2],
                "overall_avg_score": basic_stats[3],
                "timespan_days": (basic_stats[2] - basic_stats[1]) / 86400 if basic_stats[1] and basic_stats[2] else 0
            },
            "improvement_trend": {
                "early_avg_score": early_avg,
                "recent_avg_score": recent_avg,
                "improvement": ((recent_avg - early_avg) / abs(early_avg)) * 100 if early_avg and recent_avg and early_avg != 0 else 0
            },
            "reward_analytics": {
                "avg_total_reward": reward_stats[0],
                "avg_outcome_reward": reward_stats[1],
                "avg_process_reward": reward_stats[2],
                "avg_cost_penalty": reward_stats[3],
                "total_variants_with_rewards": reward_stats[4],
                "reward_progression": reward_progression,
                "top_operators_by_reward": top_operators_by_reward
            },
            "score_progression": score_progression,
            "top_operators": top_operators,
            "task_performance": task_performance
        }
    finally:
        c.close()

def clear_operator_stats():
    """Clear all operator statistics to reset learning state."""
    c = _conn()
    try:
        c.execute("DELETE FROM operator_stats")
        c.execute("DELETE FROM operator_engine_stats") 
        c.execute("DELETE FROM chat_temp_stats")
        c.commit()
        return {"cleared": True, "message": "All operator learning stats cleared"}
    finally:
        c.close()
