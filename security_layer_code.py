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
    """Құпия сөзді қауіпсіз хэштеу (SHA-256)"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def connect_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect_db() as conn:
        # Жұмыстар кестесі
        conn.execute("""CREATE TABLE IF NOT EXISTS results (
            id TEXT PRIMARY KEY, student_code TEXT NOT NULL, task_text TEXT NOT NULL,
            descriptors TEXT, proposed_score REAL NOT NULL, max_score REAL NOT NULL,
            explanation TEXT, status TEXT NOT NULL, approved_by TEXT,
            teacher_score REAL, teacher_comment TEXT, created_at TEXT NOT NULL,
            approved_at TEXT)""")
            
        # Аудит лог кестесі
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, result_id TEXT NOT NULL,
            action TEXT NOT NULL, actor_id TEXT, details TEXT, created_at TEXT NOT NULL)""")
            
        # Пайдаланушылар мен олардың кредиттер (баланс) кестесі
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            credits REAL DEFAULT 5.0,
            role TEXT DEFAULT 'teacher',
            created_at TEXT NOT NULL)""")
            
        # Әдепкі әкімші/мұғалім тіркеу (егер база бос болса)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_hash = hash_password("smarttest2026")
            conn.execute("""INSERT INTO users (username, password_hash, full_name, credits, role, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)""", 
                         ("teacher", default_hash, "Бас мұғалім", 10.0, "admin", now()))

# --- ПАЙДАЛАНУШЫЛАР МЕН КРЕДИТТЕРДІ БАСҚАРУ ---

def register_user(username, password, full_name="", initial_credits=5.0):
    """Жаңа пайдаланушыны тіркеу"""
    username = username.strip().lower()
    if not username or not password:
        raise ValueError("Логин мен құпия сөз бос болмауы тиіс")
    
    pwd_hash = hash_password(password)
    with connect_db() as conn:
        row = conn.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
        if row:
            raise ValueError("Бұл логин жүйеде тіркеліп қойған")
            
        conn.execute("""INSERT INTO users (username, password_hash, full_name, credits, role, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                     (username, pwd_hash, full_name, float(initial_credits), "teacher", now()))

def verify_user(username, password):
    """Пайдаланушыны тексеру (Логин/Пароль)"""
    username = username.strip().lower()
    pwd_hash = hash_password(password)
    with connect_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?", 
                            (username, pwd_hash)).fetchone()
        return dict(user) if user else None

def get_user_credits(username):
    """Пайдаланушының ағымдағы балансын/кредитін алу"""
    username = username.strip().lower()
    with connect_db() as conn:
        row = conn.execute("SELECT credits FROM users WHERE username=?", (username,)).fetchone()
        return float(row["credits"]) if row else 0.0

def deduct_credit(username, amount=1.0):
    """ЖИ арқылы тексергені үшін баланстан кредит шегеру"""
    username = username.strip().lower()
    current_credits = get_user_credits(username)
    if current_credits < amount:
        raise ValueError("Баланста кредит жеткіліксіз")
        
    with connect_db() as conn:
        conn.execute("UPDATE users SET credits = credits - ? WHERE username=?", (float(amount), username))
        conn.commit()
    return current_credits - amount

def add_credits(username, amount):
    """Балансты толықтыру (мысалы, төлем жасалған соң)"""
    username = username.strip().lower()
    with connect_db() as conn:
        conn.execute("UPDATE users SET credits = credits + ? WHERE username=?", (float(amount), username))
        conn.commit()

# --- ТЕКСЕРУ НӘТИЖЕЛЕРІН БАСҚАРУ ---

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