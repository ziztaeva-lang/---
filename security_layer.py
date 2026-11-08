import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
import os
import hashlib

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "smarttest.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now().isoformat(timespec="seconds")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

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
            
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            subject TEXT DEFAULT NULL,
            credits REAL DEFAULT 5.0,
            role TEXT DEFAULT 'teacher',
            created_at TEXT NOT NULL)""")
            
        # Ескі база болса, subject бағаны бар ма, соны тексеріп, жоқ болса қосамыз (миграция)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if "subject" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN subject TEXT DEFAULT NULL")

        conn.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount_tenge REAL NOT NULL,
            credits_added REAL NOT NULL,
            payment_id TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
            
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            # ӘКІМШІ РЕТІНДЕ Zoya ТІРКЕЛЕДІ
            default_hash = hash_password("zoya_2026") # Құпия сөзді өзгерте аласыз
            conn.execute("""INSERT INTO users (username, password_hash, full_name, subject, credits, role, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                         ("zoya", default_hash, "Зоя Әкімші", "Барлық пәндер", 20.0, "admin", now()))

def verify_user(username, password):
    username = username.strip().lower()
    pwd_hash = hash_password(password)
    with connect_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?", 
                            (username, pwd_hash)).fetchone()
        return dict(user) if user else None

def get_user_role(username):
    """Пайдаланушының рөлін (admin/teacher) анықтау"""
    username = username.strip().lower()
    with connect_db() as conn:
        row = conn.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        if row and row["role"]:
            return row["role"].strip().lower()
    return "teacher"

def get_user_subject(username):
    """Мұғалімге бекітілген пәнді анықтау"""
    username = username.strip().lower()
    with connect_db() as conn:
        row = conn.execute("SELECT subject FROM users WHERE username=?", (username,)).fetchone()
        if row and row["subject"]:
            return row["subject"].strip()
    return None

def set_user_subject(username, subject_name):
    """Мұғалімге пән бекіту немесе өзгерту"""
    username = username.strip().lower()
    with connect_db() as conn:
        conn.execute("UPDATE users SET subject=? WHERE username=?", (subject_name, username))
        conn.commit()

def create_user(username, password, full_name, subject=None, role="teacher", initial_credits=5.0):
    """Жаңа мұғалім тіркеу функциясы (Админ үшін)"""
    username = username.strip().lower()
    pwd_hash = hash_password(password)
    with connect_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users (username, password_hash, full_name, subject, credits, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, pwd_hash, full_name, subject, float(initial_credits), role, now()))
        conn.commit()

def get_user_credits(username):
    username = username.strip().lower()
    with connect_db() as conn:
        row = conn.execute("SELECT credits FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return float(row["credits"])
        else:
            pwd_hash = hash_password("default")
            conn.execute("INSERT OR IGNORE INTO users (username, password_hash, credits, created_at) VALUES (?, ?, ?, ?)",
                         (username, pwd_hash, 5.0, now()))
            conn.commit()
            return 5.0

def deduct_credit(username, amount=1.0):
    username = username.strip().lower()
    current_credits = get_user_credits(username)
    if current_credits < amount:
        raise ValueError("Баланста кредит жеткіліксіз")
        
    with connect_db() as conn:
        conn.execute("UPDATE users SET credits = credits - ? WHERE username=?", (float(amount), username))
        conn.commit()
    return current_credits - amount

def add_payment_record(username, amount_tenge, credits_added, payment_id):
    username = username.strip().lower()
    with connect_db() as conn:
        conn.execute("""
            INSERT INTO payments (username, amount_tenge, credits_added, payment_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (username, float(amount_tenge), float(credits_added), str(payment_id), now()))
        
        conn.execute("""
            UPDATE users SET credits = credits + ? WHERE username = ?
        """, (float(credits_added), username))
        
        conn.commit()

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