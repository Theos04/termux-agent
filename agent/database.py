import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._connect()
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source TEXT,
                    payload TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    payload TEXT,
                    priority INTEGER NOT NULL DEFAULT 5,
                    status TEXT NOT NULL DEFAULT 'pending',
                    scheduled_at TEXT,
                    timeout_seconds INTEGER NOT NULL DEFAULT 300,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    worker_id TEXT,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority, created_at);

                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    task_type TEXT NOT NULL,
                    payload TEXT,
                    cron_expr TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 5,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled, next_run_at);

                CREATE TABLE IF NOT EXISTS stats (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    # --- Events ---

    def insert_event(
        self, event_type: str, payload: dict, source: Optional[str] = None
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO events (event_type, source, payload, created_at) VALUES (?, ?, ?, ?)",
                (event_type, source, json.dumps(payload), utcnow()),
            )
            return cur.lastrowid

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        if event_type:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (event_type, limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # --- Tasks ---

    def insert_task(
        self,
        task_type: str,
        payload: dict,
        priority: int = 5,
        scheduled_at: Optional[str] = None,
        timeout_seconds: int = 300,
        max_retries: int = 3,
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO tasks
                   (task_type, payload, priority, status, scheduled_at,
                    timeout_seconds, max_retries, created_at)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (
                    task_type,
                    json.dumps(payload),
                    priority,
                    scheduled_at,
                    timeout_seconds,
                    max_retries,
                    utcnow(),
                ),
            )
            return cur.lastrowid

    def claim_next_task(self, worker_id: str) -> Optional[dict]:
        now = utcnow()
        with self.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM tasks
                   WHERE status = 'pending'
                     AND (scheduled_at IS NULL OR scheduled_at <= ?)
                     AND (next_retry_at IS NULL OR next_retry_at <= ?)
                   ORDER BY priority ASC, created_at ASC
                   LIMIT 1""",
                (now, now),
            ).fetchone()
            if not row:
                return None
            cur = conn.execute(
                """UPDATE tasks SET status = 'running', worker_id = ?, started_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (worker_id, now, row["id"]),
            )
            if cur.rowcount != 1:
                return None
            updated = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (row["id"],)
            ).fetchone()
            if updated and updated["worker_id"] == worker_id:
                return self._row_to_dict(updated)
            return None

    def complete_task(self, task_id: int, result: Any) -> None:
        with self.transaction() as conn:
            conn.execute(
                """UPDATE tasks SET status = 'completed', result = ?, completed_at = ?
                   WHERE id = ? AND status = 'running'""",
                (json.dumps(result) if result is not None else None, utcnow(), task_id),
            )

    def fail_task(
        self,
        task_id: int,
        error: str,
        retry: bool,
        next_retry_at: Optional[str] = None,
    ) -> None:
        with self.transaction() as conn:
            if retry:
                conn.execute(
                    """UPDATE tasks SET status = 'pending', error = ?,
                       retry_count = retry_count + 1, next_retry_at = ?,
                       worker_id = NULL, started_at = NULL
                       WHERE id = ?""",
                    (error, next_retry_at, task_id),
                )
            else:
                conn.execute(
                    """UPDATE tasks SET status = 'failed', error = ?, completed_at = ?
                       WHERE id = ?""",
                    (error, utcnow(), task_id),
                )

    def timeout_task(self, task_id: int) -> None:
        with self.transaction() as conn:
            conn.execute(
                """UPDATE tasks SET status = 'timeout', error = 'Task timed out',
                   completed_at = ? WHERE id = ?""",
                (utcnow(), task_id),
            )

    def get_task(self, task_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count_tasks_by_status(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # --- Schedules ---

    def insert_schedule(
        self,
        name: str,
        task_type: str,
        cron_expr: str,
        payload: dict,
        priority: int = 5,
        next_run_at: Optional[str] = None,
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO schedules
                   (name, task_type, payload, cron_expr, priority, next_run_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    task_type,
                    json.dumps(payload),
                    cron_expr,
                    priority,
                    next_run_at,
                    utcnow(),
                ),
            )
            return cur.lastrowid

    def get_due_schedules(self) -> list[dict]:
        now = utcnow()
        rows = self.conn.execute(
            """SELECT * FROM schedules
               WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)""",
            (now,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_schedule_run(self, schedule_id: int, next_run_at: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?""",
                (utcnow(), next_run_at, schedule_id),
            )

    def get_schedules(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM schedules ORDER BY name"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def set_schedule_enabled(self, name: str, enabled: bool) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE schedules SET enabled = ? WHERE name = ?",
                (1 if enabled else 0, name),
            )

    # --- Stats ---

    def increment_stat(self, key: str, amount: int = 1) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO stats (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                   value = value + excluded.value, updated_at = excluded.updated_at""",
                (key, amount, utcnow()),
            )

    def get_stats(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT key, value FROM stats").fetchall()
        return {r["key"]: r["value"] for r in rows}

    @staticmethod
    def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        for field in ("payload", "result"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
