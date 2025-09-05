import os, sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "todo.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY, text TEXT, done INTEGER DEFAULT 0)")
    return c

def add(text: str):
    c = _conn()
    c.execute("INSERT INTO todos(text,done) VALUES(?,0)", (text,))
    c.commit()
    c.close()

def list_all():
    c = _conn()
    cur = c.execute("SELECT id,text,done FROM todos ORDER BY id DESC")
    rows = [{"id": r[0], "text": r[1], "done": bool(r[2])} for r in cur.fetchall()]
    c.close()
    return rows

def complete(id: int):
    c = _conn()
    c.execute("UPDATE todos SET done=1 WHERE id=?", (id,))
    c.commit()
    c.close()

def delete(id: int):
    c = _conn()
    c.execute("DELETE FROM todos WHERE id=?", (id,))
    c.commit()
    c.close()