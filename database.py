import os
import sqlite3
import json
import bcrypt
from datetime import datetime, timezone
from config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                last_login TEXT
            );
            CREATE TABLE IF NOT EXISTS cvs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                prompt TEXT NOT NULL,
                name TEXT NOT NULL,
                specialization TEXT NOT NULL,
                experience TEXT,
                languages TEXT,
                frameworks TEXT,
                libraries TEXT,
                other_skills TEXT,
                projects TEXT NOT NULL,
                docx_path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_by INTEGER REFERENCES users(id),
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                cv_id INTEGER,
                detail TEXT,
                created_at TEXT NOT NULL
            );
        """)
        # Default settings
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deepseek_api_key', '')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deepseek_model', 'deepseek-chat')")
        # Seed admin user
        exists = conn.execute("SELECT 1 FROM users WHERE login='admin'").fetchone()
        if not exists:
            pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt(rounds=12)).decode()
            conn.execute(
                "INSERT INTO users (login, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                ("admin", pw_hash, "admin", _now())
            )
        conn.commit()


# ── Users ──────────────────────────────────────────────────────────────────

def get_user_by_login(login: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE login=?", (login,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def create_user(login: str, password_hash: str, role: str = "user") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (login, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (login, password_hash, role, _now())
        )
        conn.commit()
        return cur.lastrowid


def update_user_password(user_id: int, password_hash: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
        conn.commit()


def delete_user(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()


def update_last_login(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), user_id))
        conn.commit()


# ── CVs ────────────────────────────────────────────────────────────────────

def create_cv(created_by: int, prompt: str, cv_data: dict, docx_path: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO cvs
              (created_by, created_at, updated_at, prompt, name, specialization,
               experience, languages, frameworks, libraries, other_skills, projects, docx_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            created_by, _now(), _now(), prompt,
            cv_data["name"], cv_data["specialization"],
            cv_data.get("experience", ""), cv_data.get("languages", ""),
            cv_data.get("frameworks", ""), cv_data.get("libraries", ""),
            cv_data.get("other_skills", ""),
            json.dumps(cv_data.get("projects", []), ensure_ascii=False),
            docx_path,
        ))
        conn.commit()
        return cur.lastrowid


def get_cv(cv_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cvs WHERE id=?", (cv_id,)).fetchone()
        if not row:
            return None
        cv = dict(row)
        cv["projects"] = json.loads(cv["projects"])
        return cv


def list_cvs(name: str = "", spec: str = "", stack: str = "", sort: str = "desc") -> list[dict]:
    query = "SELECT * FROM cvs WHERE 1=1"
    params: list = []
    if name:
        query += " AND name LIKE ?"
        params.append(f"%{name}%")
    if spec:
        query += " AND specialization LIKE ?"
        params.append(f"%{spec}%")
    if stack:
        query += " AND (languages LIKE ? OR frameworks LIKE ? OR libraries LIKE ?)"
        params.extend([f"%{stack}%"] * 3)
    order = "DESC" if sort != "asc" else "ASC"
    query += f" ORDER BY created_at {order}"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            cv = dict(row)
            cv["projects"] = json.loads(cv["projects"])
            result.append(cv)
        return result


def update_cv(cv_id: int, cv_data: dict, docx_path: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE cvs SET updated_at=?, name=?, specialization=?, experience=?,
              languages=?, frameworks=?, libraries=?, other_skills=?, projects=?, docx_path=?
            WHERE id=?
        """, (
            _now(), cv_data["name"], cv_data["specialization"],
            cv_data.get("experience", ""), cv_data.get("languages", ""),
            cv_data.get("frameworks", ""), cv_data.get("libraries", ""),
            cv_data.get("other_skills", ""),
            json.dumps(cv_data.get("projects", []), ensure_ascii=False),
            docx_path, cv_id,
        ))
        conn.commit()


def delete_cv(cv_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM cvs WHERE id=?", (cv_id,))
        conn.commit()


# ── Settings ───────────────────────────────────────────────────────────────

_ENV_KEYS = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_model": "DEEPSEEK_MODEL",
}


def get_setting(key: str) -> str:
    # Environment variable takes priority (works on Render / any cloud host)
    env_val = os.environ.get(_ENV_KEYS.get(key, ""))
    if env_val:
        return env_val
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else ""


def set_setting(key: str, value: str, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_by, updated_at) VALUES (?,?,?,?)",
            (key, value, user_id, _now())
        )
        conn.commit()


# ── Action Log ─────────────────────────────────────────────────────────────

def log_action(user_id: int, action: str, cv_id: int | None = None, detail: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO action_log (user_id, action, cv_id, detail, created_at) VALUES (?,?,?,?,?)",
            (user_id, action, cv_id, detail, _now())
        )
        conn.commit()


def get_stats() -> dict:
    with get_conn() as conn:
        total_cvs = conn.execute("SELECT COUNT(*) FROM cvs").fetchone()[0]
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_downloads = conn.execute(
            "SELECT COUNT(*) FROM action_log WHERE action='download'"
        ).fetchone()[0]
        recent = conn.execute("""
            SELECT al.action, al.cv_id, al.detail, al.created_at, u.login
            FROM action_log al JOIN users u ON al.user_id=u.id
            ORDER BY al.created_at DESC LIMIT 20
        """).fetchall()
        return {
            "total_cvs": total_cvs,
            "total_users": total_users,
            "total_downloads": total_downloads,
            "recent_actions": [dict(r) for r in recent],
        }
