import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "smarttest.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now().isoformat(timespec="seconds")

def connect_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS results (
            id TEXT PRIMARY KEY, student_code TEXT NOT NULL, task_text TEXT NOT NULL,
            descriptors TEXT, proposed_score REAL NOT NULL, max_score REAL NOT NULL,
            explanation TEXT, status TEXT NOT NULL, approved_by TEXT,
            teacher_score REAL, teacher_comment TEXT, created_at TEXT NOT NULL,
            approved_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, result_id TEXT NOT NULL,
            action TEXT NOT NULL, actor_id TEXT, details TEXT, created_at TEXT NOT NULL)""")

def save_pending_result(student_code, task_text, descriptors, proposed_score, max_score, explanation):
    if not student_code or not student_code.strip():
        raise ValueError("Анонимді код міндетті")
    if not 0 <= float(proposed_score) <= float(max_score):
        raise ValueError("Ұпай рұқсат етілген аралықта емес")
    rid = str(uuid.uuid4())
    with connect_db() as conn:
        conn.execute("""INSERT INTO results
        (id, student_code, task_text, descriptors, proposed_score, max_score, explanation, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rid, student_code, task_text, descriptors, float(proposed_score), float(max_score),
         explanation, "Мұғалім тексеруін күтуде", now()))
        conn.execute("""INSERT INTO audit_log (result_id, action, actor_id, details, created_at)
        VALUES (?, ?, ?, ?, ?)""", (rid, "Жұмыс сақталды", None, "Қорытынды баға бекітілмеген", now()))
    return rid

def get_pending_results():
    with connect_db() as conn:
        return conn.execute("SELECT * FROM results WHERE status=? ORDER BY created_at DESC",
                            ("Мұғалім тексеруін күтуде",)).fetchall()

def approve_result(result_id, teacher_score, teacher_id, teacher_comment=""):
    if not teacher_id or not teacher_id.strip():
        raise PermissionError("Мұғалім ID-і қажет")
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM results WHERE id=?", (result_id,)).fetchone()
        if row is None:
            raise ValueError("Жұмыс табылмады")
        if row["status"] != "Мұғалім тексеруін күтуде":
            raise ValueError("Жұмыс бұрын бекітілген немесе жабылған")
        score = float(teacher_score)
        if not 0 <= score <= float(row["max_score"]):
            raise ValueError("Ұпай рұқсат етілген аралықта емес")
        stamp = now()
        conn.execute("""UPDATE results SET status=?, teacher_score=?, approved_by=?,
        teacher_comment=?, approved_at=? WHERE id=?""",
        ("Мұғалім бекітті", score, teacher_id.strip(), teacher_comment, stamp, result_id))
        conn.execute("""INSERT INTO audit_log (result_id, action, actor_id, details, created_at)
        VALUES (?, ?, ?, ?, ?)""",
        (result_id, "Бағаны бекіту", teacher_id.strip(), f"Мұғалім бекіткен ұпай: {score}", stamp))

def get_approved_results():
    with connect_db() as conn:
        return conn.execute("SELECT * FROM results WHERE status=? ORDER BY approved_at DESC",
                            ("Мұғалім бекітті",)).fetchall()

def external_ai_is_enabled():
    return os.environ.get("SMARTTEST_EXTERNAL_AI", "0") == "1"
