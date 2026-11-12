"""客户数据中台（SQLite 版）。

生产环境这里是后端团队维护的 CRM 服务；本项目用 SQLite 落一份，
保证「客户档案 / 待办 / 风险 / 文书版本」可持久化、可查询、可交接。
所有 Agent 都读写同一份数据 —— 这是解决"跨岗位信息孤岛"的关键。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name        TEXT,
    stage       TEXT,
    owner       TEXT DEFAULT '',
    data        TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS users (
    username     TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role         TEXT DEFAULT 'advisor',
    display_name TEXT DEFAULT '',
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    customer_id TEXT,
    title       TEXT,
    level       TEXT,
    owner       TEXT,
    due_date    TEXT,
    source      TEXT,
    status      TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS risks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT,
    tag         TEXT,
    level       TEXT,
    reason      TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS doc_versions (
    version_id  TEXT PRIMARY KEY,
    customer_id TEXT,
    doc_type    TEXT,
    content     TEXT,
    status      TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS interview_sessions (
    session_id  TEXT PRIMARY KEY,
    customer_id TEXT,
    data        TEXT,
    created_at  TEXT
);
"""


class Storage:
    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path or settings.runtime_dir / "crm.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """老库补字段：customers.owner（鉴权上线后才有）。"""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(customers)")}
        if "owner" not in columns:
            self._conn.execute("ALTER TABLE customers ADD COLUMN owner TEXT DEFAULT ''")

    # ---------------- 用户 ----------------
    def create_user(self, username: str, password_hash: str, role: str = "advisor",
                    display_name: str = "") -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users(username,password_hash,role,display_name,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (username, password_hash, role, display_name, _now()))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user(self, username: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT username,role,display_name,created_at FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]

    def ensure_default_users(self, admin: str, admin_password: str,
                             extras: list[tuple[str, str, str, str]] | None = None) -> int:
        """首次启动建默认账号；已存在则不动（不覆盖用户改过的密码）。"""
        from .auth import hash_password

        created = 0
        if not self.get_user(admin):
            created += int(self.create_user(admin, hash_password(admin_password),
                                            role="admin", display_name="机构负责人"))
        for username, password, role, name in (extras or []):
            if not self.get_user(username):
                created += int(self.create_user(username, hash_password(password),
                                                role=role, display_name=name))
        return created

    # ---------------- 客户 ----------------
    def save_customer(self, state) -> None:
        payload = state.model_dump() if hasattr(state, "model_dump") else dict(state)
        owner = payload.get("owner", "") or ""
        with self._lock:
            self._conn.execute(
                "INSERT INTO customers(customer_id,name,stage,owner,data,updated_at)"
                " VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(customer_id) DO UPDATE SET name=?, stage=?, owner=?, data=?, updated_at=?",
                (payload["customer_id"], payload.get("customer_name", ""), payload.get("stage", ""),
                 owner, json.dumps(payload, ensure_ascii=False, default=str), _now(),
                 payload.get("customer_name", ""), payload.get("stage", ""), owner,
                 json.dumps(payload, ensure_ascii=False, default=str), _now()),
            )
            self._conn.commit()
        for task in payload.get("task_list", []):
            self.add_task(task)
        for tag in payload.get("risk_tags", []):
            self.add_risk(payload["customer_id"], tag)

    def load_customer(self, customer_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_customers(self, limit: int = 100, owner: str | None = None) -> list[dict]:
        sql = ("SELECT customer_id,name,stage,owner,updated_at FROM customers "
               "WHERE 1=1")
        args: list = []
        if owner:
            sql += " AND owner=?"
            args.append(owner)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def list_customer_data(self, limit: int = 500) -> list[dict]:
        """取全部客户的完整档案（含 agent_outputs），给看板做流程完成度统计。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM customers ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            try:
                out.append(json.loads(row["data"]))
            except (TypeError, json.JSONDecodeError):
                continue
        return out

    def clear_all(self) -> dict:
        """清空全部客户数据（不删文件，服务在跑也能执行）。"""
        counts = {}
        with self._lock:
            for table in ("customers", "tasks", "risks", "doc_versions"):
                cur = self._conn.execute(f"DELETE FROM {table}")
                counts[table] = cur.rowcount
            self._conn.commit()
        return counts

    def clear_customer_artifacts(self, customer_id: str, keep_versions: bool = True) -> dict:
        """重跑前清掉待办与风险（文书版本属于历史档案，默认保留）。"""
        removed = {}
        with self._lock:
            cur = self._conn.execute("DELETE FROM tasks WHERE customer_id=?", (customer_id,))
            removed["tasks"] = cur.rowcount
            cur = self._conn.execute("DELETE FROM risks WHERE customer_id=?", (customer_id,))
            removed["risks"] = cur.rowcount
            if not keep_versions:
                cur = self._conn.execute("DELETE FROM doc_versions WHERE customer_id=?", (customer_id,))
                removed["doc_versions"] = cur.rowcount
            self._conn.commit()
        return removed

    # ---------------- 待办 ----------------
    def add_task(self, task: dict) -> str:
        task_id = task.get("task_id") or f"task-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO tasks(task_id,customer_id,title,level,owner,due_date,source,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, task.get("customer_id", ""), task.get("title", ""), task.get("level", "普通"),
                 task.get("owner", "顾问"), task.get("due_date", ""), task.get("source", ""),
                 task.get("status", "open"), _now()),
            )
            self._conn.commit()
        return task_id

    def list_tasks(self, customer_id: str | None = None, level: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM tasks WHERE 1=1", []
        if customer_id:
            sql += " AND customer_id=?"
            args.append(customer_id)
        if level:
            sql += " AND level=?"
            args.append(level)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 风险 ----------------
    def add_risk(self, customer_id: str, tag: str, level: str = "中", reason: str = "") -> None:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM risks WHERE customer_id=? AND tag=? LIMIT 1",
                (customer_id, tag)).fetchone()
            if exists:
                return
            self._conn.execute(
                "INSERT INTO risks(customer_id,tag,level,reason,created_at) VALUES(?,?,?,?,?)",
                (customer_id, tag, level, reason, _now()))
            self._conn.commit()

    def list_risks(self, customer_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM risks WHERE 1=1", []
        if customer_id:
            sql += " AND customer_id=?"
            args.append(customer_id)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 文书版本 ----------------
    def save_version(self, customer_id: str, doc_type: str, content: str,
                     status: str = "待修改") -> str:
        version_id = f"{doc_type}-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
        with self._lock:
            self._conn.execute(
                "INSERT INTO doc_versions(version_id,customer_id,doc_type,content,status,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (version_id, customer_id, doc_type, content, status, _now()))
            self._conn.commit()
        return version_id

    def list_versions(self, customer_id: str, doc_type: str | None = None) -> list[dict]:
        sql = ("SELECT version_id,doc_type,status,created_at,length(content) AS chars "
               "FROM doc_versions WHERE customer_id=?")
        args: list = [customer_id]
        if doc_type:
            sql += " AND doc_type=?"
            args.append(doc_type)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def update_version_status(self, customer_id: str, version_id: str, status: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE doc_versions SET status=? WHERE customer_id=? AND version_id=?",
                (status, customer_id, version_id))
            self._conn.commit()
        return cur.rowcount > 0

    def get_version_content(self, version_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT content FROM doc_versions WHERE version_id=?", (version_id,)).fetchone()
        return row["content"] if row else None

    # ---------------- 模拟面试 ----------------
    def save_interview(self, session) -> str:
        payload = session.model_dump() if hasattr(session, "model_dump") else dict(session)
        with self._lock:
            self._conn.execute(
                "INSERT INTO interview_sessions(session_id,customer_id,data,created_at)"
                " VALUES(?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET data=?, created_at=?",
                (payload["session_id"], payload.get("customer_id", ""),
                 json.dumps(payload, ensure_ascii=False, default=str), _now(),
                 json.dumps(payload, ensure_ascii=False, default=str), _now()))
            self._conn.commit()
        return payload["session_id"]

    def load_interview(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM interview_sessions WHERE session_id=?", (session_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_interviews(self, customer_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id,customer_id,created_at FROM interview_sessions"
                " WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self._lock:
            out = {}
            for table in ("customers", "tasks", "risks", "doc_versions"):
                out[table] = self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        return out


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
