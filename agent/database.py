import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

log = logging.getLogger(__name__)


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

                CREATE TABLE IF NOT EXISTS places (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    phone       TEXT,
                    address     TEXT,
                    category    TEXT,
                    rating      REAL,
                    reviews     INTEGER,
                    maps_url    TEXT,
                    query       TEXT,
                    source      TEXT DEFAULT 'google_maps',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    UNIQUE(name, phone)
                );
                CREATE INDEX IF NOT EXISTS idx_places_phone   ON places(phone);
                CREATE INDEX IF NOT EXISTS idx_places_query   ON places(query);
                CREATE INDEX IF NOT EXISTS idx_places_created ON places(created_at);

                -- ── WhatsApp & Pharmacy Trading Schema ─────────────────────
                CREATE TABLE IF NOT EXISTS contacts (
                    id                  TEXT PRIMARY KEY,
                    whatsapp_id         TEXT UNIQUE NOT NULL,
                    display_name        TEXT,
                    verification_status TEXT NOT NULL DEFAULT 'unverified',
                    created_at          TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_contacts_whatsapp ON contacts(whatsapp_id);

                CREATE TABLE IF NOT EXISTS businesses (
                    id              TEXT PRIMARY KEY,
                    legal_name      TEXT NOT NULL,
                    business_type   TEXT NOT NULL,
                    license_number  TEXT,
                    license_status  TEXT NOT NULL DEFAULT 'pending',
                    status          TEXT NOT NULL DEFAULT 'pending',
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contact_roles (
                    contact_id      TEXT NOT NULL,
                    business_id     TEXT NOT NULL,
                    role            TEXT NOT NULL,
                    approved_by     TEXT,
                    approved_at     TEXT,
                    PRIMARY KEY (contact_id, business_id, role),
                    FOREIGN KEY (contact_id) REFERENCES contacts(id),
                    FOREIGN KEY (business_id) REFERENCES businesses(id)
                );

                CREATE TABLE IF NOT EXISTS messaging_preferences (
                    contact_id      TEXT NOT NULL,
                    purpose         TEXT NOT NULL,
                    consent_status  TEXT NOT NULL,
                    updated_at      TEXT NOT NULL,
                    PRIMARY KEY (contact_id, purpose),
                    FOREIGN KEY (contact_id) REFERENCES contacts(id)
                );

                CREATE TABLE IF NOT EXISTS products (
                    id              TEXT PRIMARY KEY,
                    canonical_name  TEXT NOT NULL,
                    brand           TEXT,
                    ingredient      TEXT,
                    strength        TEXT,
                    dosage_form     TEXT,
                    pack_size       TEXT,
                    manufacturer    TEXT,
                    schedule_class  TEXT DEFAULT 'OTC',
                    active          INTEGER NOT NULL DEFAULT 1,
                    created_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_products_canonical ON products(canonical_name);
                CREATE INDEX IF NOT EXISTS idx_products_brand     ON products(brand);

                CREATE TABLE IF NOT EXISTS inventory_batches (
                    id                  TEXT PRIMARY KEY,
                    product_id          TEXT NOT NULL,
                    batch_number        TEXT NOT NULL,
                    expiry_date         TEXT NOT NULL,
                    quantity_on_hand    REAL NOT NULL DEFAULT 0,
                    quantity_reserved   REAL NOT NULL DEFAULT 0,
                    purchase_price      REAL,
                    received_at         TEXT,
                    FOREIGN KEY (product_id) REFERENCES products(id)
                );
                CREATE INDEX IF NOT EXISTS idx_batches_product ON inventory_batches(product_id);
                CREATE INDEX IF NOT EXISTS idx_batches_expiry  ON inventory_batches(expiry_date);

                CREATE TABLE IF NOT EXISTS supplier_quotes (
                    id                   TEXT PRIMARY KEY,
                    supplier_business_id TEXT NOT NULL,
                    product_id           TEXT NOT NULL,
                    supplier_sku         TEXT,
                    pack_size            TEXT NOT NULL,
                    quoted_quantity      REAL NOT NULL,
                    unit_rate            REAL NOT NULL,
                    tax_details          TEXT,
                    expiry_date          TEXT,
                    delivery_eta         TEXT,
                    status               TEXT NOT NULL DEFAULT 'received',
                    source_message_id    TEXT,
                    created_at           TEXT NOT NULL,
                    FOREIGN KEY (supplier_business_id) REFERENCES businesses(id),
                    FOREIGN KEY (product_id) REFERENCES products(id)
                );
                CREATE INDEX IF NOT EXISTS idx_quotes_product ON supplier_quotes(product_id);

                CREATE TABLE IF NOT EXISTS sales_orders (
                    id                  TEXT PRIMARY KEY,
                    buyer_business_id   TEXT NOT NULL,
                    delivery_address    TEXT,
                    status              TEXT NOT NULL DEFAULT 'draft',
                    currency            TEXT NOT NULL DEFAULT 'INR',
                    total_amount        REAL,
                    items               TEXT,
                    approved_by         TEXT,
                    created_at          TEXT NOT NULL,
                    updated_at          TEXT NOT NULL,
                    FOREIGN KEY (buyer_business_id) REFERENCES businesses(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sales_orders_buyer ON sales_orders(buyer_business_id);

                CREATE TABLE IF NOT EXISTS purchase_orders (
                    id                   TEXT PRIMARY KEY,
                    supplier_business_id TEXT NOT NULL,
                    status               TEXT NOT NULL DEFAULT 'draft',
                    total_amount         REAL,
                    items                TEXT,
                    approved_by          TEXT,
                    created_at           TEXT NOT NULL,
                    updated_at           TEXT NOT NULL,
                    FOREIGN KEY (supplier_business_id) REFERENCES businesses(id)
                );

                CREATE TABLE IF NOT EXISTS inventory_movements (
                    id              TEXT PRIMARY KEY,
                    batch_id        TEXT NOT NULL,
                    movement_type   TEXT NOT NULL,
                    quantity_delta  REAL NOT NULL,
                    reference_type  TEXT NOT NULL,
                    reference_id    TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (batch_id) REFERENCES inventory_batches(id)
                );

                CREATE TABLE IF NOT EXISTS message_inbox (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_message_id TEXT UNIQUE NOT NULL,
                    contact_id          TEXT,
                    sender_phone        TEXT NOT NULL,
                    payload             TEXT NOT NULL,
                    status              TEXT NOT NULL DEFAULT 'received',
                    received_at         TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_outbox (
                    id                  TEXT PRIMARY KEY,
                    idempotency_key     TEXT UNIQUE NOT NULL,
                    recipient_id        TEXT,
                    recipient_phone     TEXT NOT NULL,
                    payload             TEXT NOT NULL,
                    status              TEXT NOT NULL DEFAULT 'pending',
                    attempts            INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at     TEXT,
                    provider_message_id TEXT,
                    created_at          TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_status ON message_outbox(status, next_attempt_at);

                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id            TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    business_key  TEXT NOT NULL,
                    state         TEXT NOT NULL,
                    next_run_at   TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    state_data    TEXT NOT NULL DEFAULT '{}',
                    updated_at    TEXT NOT NULL,
                    UNIQUE (workflow_type, business_key)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_type    TEXT NOT NULL,
                    actor_id      TEXT,
                    action        TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id   TEXT NOT NULL,
                    outcome       TEXT NOT NULL,
                    metadata      TEXT,
                    created_at    TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);

                """
            )
            conn.commit()

        # Safe migration: add gcal_event_id column if it doesn't exist yet.
        # SQLite does not support IF NOT EXISTS on ALTER TABLE, so we use
        # a try/except approach that is safe to run on every startup.
        with self._connect() as conn:
            try:
                conn.execute("ALTER TABLE schedules ADD COLUMN gcal_event_id TEXT")
                conn.commit()
                log.debug("Migrated schedules: added gcal_event_id column")
            except sqlite3.OperationalError:
                pass  # column already exists

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

    def delete_schedule(self, name: str) -> bool:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM schedules WHERE name = ?", (name,))
            return cur.rowcount > 0

    def get_schedule_by_name(self, name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM schedules WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def set_schedule_gcal_event(self, name: str, gcal_event_id: str) -> None:
        """Store the Google Calendar event ID for a named schedule."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE schedules SET gcal_event_id = ? WHERE name = ?",
                (gcal_event_id, name),
            )

    def get_schedule_gcal_event(self, name: str) -> Optional[str]:
        """Return the Google Calendar event ID linked to a schedule, or None."""
        row = self.conn.execute(
            "SELECT gcal_event_id FROM schedules WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return row["gcal_event_id"] or None

    # --- Places ---

    def store_places(
        self,
        cards: list[dict],
        *,
        query: str = "",
        source: str = "google_maps",
    ) -> dict[str, int]:
        """Upsert a list of place cards into the places table.

        Returns a dict with ``inserted`` and ``updated`` counts.
        Rows are matched on (name, phone); a NULL phone is treated as a distinct
        value so two phone-less entries with the same name still merge.
        """
        inserted = updated = 0
        now = utcnow()
        for card in cards:
            name = (card.get("name") or "").strip()
            if not name:
                continue
            phone = (card.get("phone") or "").strip() or None
            address = (card.get("address") or "").strip() or None
            category = (card.get("category") or "").strip() or None
            rating = card.get("rating")
            reviews = card.get("reviews")
            maps_url = (card.get("maps_url") or "").strip() or None

            with self.transaction() as conn:
                # Check if row already exists
                existing = conn.execute(
                    "SELECT id FROM places WHERE name = ? AND (phone = ? OR (phone IS NULL AND ? IS NULL))",
                    (name, phone, phone),
                ).fetchone()
                if existing:
                    conn.execute(
                        """UPDATE places SET
                            address   = COALESCE(?, address),
                            category  = COALESCE(?, category),
                            rating    = COALESCE(?, rating),
                            reviews   = COALESCE(?, reviews),
                            maps_url  = COALESCE(?, maps_url),
                            query     = ?,
                            updated_at = ?
                           WHERE id = ?""",
                        (address, category, rating, reviews, maps_url,
                         query or None, now, existing["id"]),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO places
                            (name, phone, address, category, rating, reviews,
                             maps_url, query, source, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (name, phone, address, category, rating, reviews,
                         maps_url, query or None, source, now, now),
                    )
                    inserted += 1
        return {"inserted": inserted, "updated": updated}

    def get_places(
        self,
        *,
        query: str | None = None,
        with_phone: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """Return places, optionally filtered by scrape query or phone presence."""
        conditions: list[str] = []
        params: list[Any] = []
        if query:
            conditions.append("query LIKE ?")
            params.append(f"%{query}%")
        if with_phone:
            conditions.append("phone IS NOT NULL AND phone != ''")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self.conn.execute(
            f"SELECT * FROM places {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_places(self, *, with_phone: bool = False) -> dict[str, int]:
        total = self.conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        phoned = self.conn.execute(
            "SELECT COUNT(*) FROM places WHERE phone IS NOT NULL AND phone != ''"
        ).fetchone()[0]
        return {"total": total, "with_phone": phoned}

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

    # --- WhatsApp & Pharmacy Trading Domain ---

    def record_audit_event(
        self,
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Immutable audit logging for all agent mutations, permissions, and handoffs."""
        now = utcnow()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO audit_events
                    (actor_type, actor_id, action, resource_type, resource_id, outcome, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (actor_type, actor_id or "system", action, resource_type, resource_id, outcome, meta_json, now),
            )
            return cur.lastrowid

    def get_audit_events(self, limit: int = 50, resource_id: Optional[str] = None) -> list[dict]:
        where = "WHERE resource_id = ?" if resource_id else ""
        params = [resource_id, limit] if resource_id else [limit]
        rows = self.conn.execute(
            f"SELECT * FROM audit_events {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except Exception:
                    pass
            result.append(d)
        return result

    def get_contact_by_phone(self, phone: str) -> Optional[dict]:
        """Find contact by whatsapp_id or stripped phone digits."""
        norm = "".join(c for c in phone if c.isdigit())
        row = self.conn.execute(
            "SELECT * FROM contacts WHERE whatsapp_id = ? OR whatsapp_id LIKE ?",
            (phone.strip(), f"%{norm[-10:]}%" if len(norm) >= 10 else f"%{phone}%"),
        ).fetchone()
        return dict(row) if row else None

    def create_or_update_contact(
        self,
        whatsapp_id: str,
        display_name: Optional[str] = None,
        verification_status: str = "unverified",
    ) -> dict:
        existing = self.get_contact_by_phone(whatsapp_id)
        now = utcnow()
        if existing:
            if display_name and not existing.get("display_name"):
                with self.transaction() as conn:
                    conn.execute(
                        "UPDATE contacts SET display_name = ? WHERE id = ?",
                        (display_name, existing["id"]),
                    )
                existing["display_name"] = display_name
            return existing

        import uuid
        cid = f"cnt_{uuid.uuid4().hex[:12]}"
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO contacts (id, whatsapp_id, display_name, verification_status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (cid, whatsapp_id.strip(), display_name, verification_status, now),
            )
        return {
            "id": cid,
            "whatsapp_id": whatsapp_id.strip(),
            "display_name": display_name,
            "verification_status": verification_status,
            "created_at": now,
        }

    def get_contact_roles(self, contact_id: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT cr.role, cr.business_id, cr.approved_by, cr.approved_at,
                      b.legal_name, b.business_type, b.license_status, b.status as business_status
               FROM contact_roles cr
               JOIN businesses b ON cr.business_id = b.id
               WHERE cr.contact_id = ?""",
            (contact_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def assign_contact_role(
        self,
        contact_id: str,
        business_id: str,
        role: str,
        approved_by: Optional[str] = None,
    ) -> None:
        now = utcnow()
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO contact_roles
                    (contact_id, business_id, role, approved_by, approved_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (contact_id, business_id, role, approved_by, now),
            )

    def search_products(self, query: str, active_only: bool = True) -> list[dict]:
        """Search products by canonical name, brand, or ingredient."""
        q = f"%{query.strip()}%"
        active_clause = "AND active = 1" if active_only else ""
        rows = self.conn.execute(
            f"""SELECT * FROM products
                WHERE (canonical_name LIKE ? OR brand LIKE ? OR ingredient LIKE ?) {active_clause}
                ORDER BY canonical_name ASC LIMIT 25""",
            (q, q, q),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_product(self, product_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None

    def get_product_batches(self, product_id: str, non_expired_only: bool = True) -> list[dict]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expiry_clause = "AND expiry_date >= ?" if non_expired_only else ""
        params = [product_id, today] if non_expired_only else [product_id]
        rows = self.conn.execute(
            f"""SELECT * FROM inventory_batches
                WHERE product_id = ? {expiry_clause}
                ORDER BY expiry_date ASC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sales_order(self, order_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM sales_orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("items"):
            try:
                d["items"] = json.loads(d["items"])
            except Exception:
                pass
        return d

    def update_sales_order_address(
        self, order_id: str, new_address: str, actor_id: Optional[str] = None
    ) -> dict:
        """Update delivery address with status check and audit trail."""
        order = self.get_sales_order(order_id)
        if not order:
            return {"ok": False, "error": f"Order {order_id} not found"}
        if order.get("status") in ("dispatched", "delivered", "cancelled"):
            return {
                "ok": False,
                "error": f"Cannot update address for order with status '{order.get('status')}'",
            }
        now = utcnow()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sales_orders SET delivery_address = ?, updated_at = ? WHERE id = ?",
                (new_address.strip(), now, order_id),
            )
        self.record_audit_event(
            actor_type="write_agent",
            actor_id=actor_id,
            action="update_delivery_address",
            resource_type="sales_order",
            resource_id=order_id,
            outcome="success",
            metadata={"prev_address": order.get("delivery_address"), "new_address": new_address},
        )
        return {"ok": True, "order_id": order_id, "delivery_address": new_address}

    def record_supplier_quote(
        self,
        supplier_business_id: str,
        product_id: str,
        quoted_quantity: float,
        unit_rate: float,
        pack_size: str,
        tax_details: Optional[dict] = None,
        expiry_date: Optional[str] = None,
        delivery_eta: Optional[str] = None,
        source_message_id: Optional[str] = None,
    ) -> dict:
        import uuid
        qid = f"quot_{uuid.uuid4().hex[:12]}"
        now = utcnow()
        tax_json = json.dumps(tax_details or {}, ensure_ascii=False)
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO supplier_quotes
                    (id, supplier_business_id, product_id, pack_size, quoted_quantity,
                     unit_rate, tax_details, expiry_date, delivery_eta, status, source_message_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?)""",
                (qid, supplier_business_id, product_id, pack_size, quoted_quantity,
                 unit_rate, tax_json, expiry_date, delivery_eta, source_message_id, now),
            )
        self.record_audit_event(
            actor_type="write_agent",
            actor_id=supplier_business_id,
            action="record_supplier_quote",
            resource_type="supplier_quote",
            resource_id=qid,
            outcome="success",
            metadata={"product_id": product_id, "unit_rate": unit_rate, "quoted_quantity": quoted_quantity},
        )
        return {"ok": True, "quote_id": qid}

    def enqueue_inbox_message(
        self,
        provider_message_id: str,
        sender_phone: str,
        payload: dict,
        contact_id: Optional[str] = None,
    ) -> int:
        now = utcnow()
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO message_inbox
                    (provider_message_id, contact_id, sender_phone, payload, status, received_at)
                   VALUES (?, ?, ?, ?, 'received', ?)""",
                (provider_message_id, contact_id, sender_phone, json.dumps(payload), now),
            )
            return cur.lastrowid

    def enqueue_outbox_message(
        self,
        idempotency_key: str,
        recipient_phone: str,
        payload: dict,
        recipient_id: Optional[str] = None,
    ) -> dict:
        import uuid
        mid = f"msg_{uuid.uuid4().hex[:12]}"
        now = utcnow()
        with self.transaction() as conn:
            # Check idempotency
            existing = conn.execute(
                "SELECT * FROM message_outbox WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing)
            conn.execute(
                """INSERT INTO message_outbox
                    (id, idempotency_key, recipient_id, recipient_phone, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (mid, idempotency_key, recipient_id, recipient_phone, json.dumps(payload), now),
            )
        return {
            "id": mid,
            "idempotency_key": idempotency_key,
            "recipient_phone": recipient_phone,
            "status": "pending",
            "created_at": now,
        }

    def get_pending_outbox_messages(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM message_outbox WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("payload"):
                try:
                    d["payload"] = json.loads(d["payload"])
                except Exception:
                    pass
            result.append(d)
        return result

    def mark_outbox_sent(self, idempotency_key: str, provider_message_id: Optional[str] = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE message_outbox SET status = 'sent', provider_message_id = ? WHERE idempotency_key = ?",
                (provider_message_id, idempotency_key),
            )

    def seed_pharmacy_demo_data(self) -> None:
        """Seed sample medicines, inventory batches, and verified contacts for testing."""
        import uuid
        now = utcnow()

        # Seed Businesses
        b_buyer_id = "biz_retail_lifecare_pune"
        b_supp_id = "biz_supp_apex_mumbai"
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO businesses
                    (id, legal_name, business_type, license_number, license_status, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (b_buyer_id, "LifeCare Chemist Pune", "retail_pharmacy", "MH-PUN-2024-9988", "verified", "active", now),
            )
            conn.execute(
                """INSERT OR REPLACE INTO businesses
                    (id, legal_name, business_type, license_number, license_status, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (b_supp_id, "Apex Pharma Distributors", "supplier", "MH-MUM-2023-1122", "verified", "active", now),
            )

        # Seed Contacts
        c_buyer = self.create_or_update_contact("+919876543210", "Rajesh Sharma (LifeCare)", "verified")
        self.assign_contact_role(c_buyer["id"], b_buyer_id, "retailer", approved_by="admin_system")

        c_supp = self.create_or_update_contact("+919822001122", "Vikram Patel (Apex Pharma)", "verified")
        self.assign_contact_role(c_supp["id"], b_supp_id, "supplier", approved_by="admin_system")

        # Seed Products
        products = [
            ("prod_pcm_500", "Paracetamol 500mg", "Crocin 500", "Paracetamol", "500 mg", "Tablet", "Strip of 15", "GSK", "OTC"),
            ("prod_amox_500", "Amoxicillin 500mg", "Mox 500", "Amoxicillin", "500 mg", "Capsule", "Strip of 10", "Sun Pharma", "Schedule H"),
            ("prod_azith_500", "Azithromycin 500mg", "Azee 500", "Azithromycin", "500 mg", "Tablet", "Strip of 5", "Cipla", "Schedule H"),
            ("prod_met_500", "Metformin 500mg", "Glycomet 500", "Metformin HCl", "500 mg", "Tablet", "Strip of 20", "USV", "Schedule H"),
        ]
        with self.transaction() as conn:
            for pid, cname, brand, ing, strg, form, pack, mfg, sclass in products:
                conn.execute(
                    """INSERT OR REPLACE INTO products
                        (id, canonical_name, brand, ingredient, strength, dosage_form, pack_size, manufacturer, schedule_class, active, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (pid, cname, brand, ing, strg, form, pack, mfg, sclass, now),
                )

        # Seed Inventory Batches
        batches = [
            ("bat_pcm_001", "prod_pcm_500", "PCM24A", "2027-08-31", 120.0, 10.0, 18.50),
            ("bat_amox_001", "prod_amox_500", "MOX24B", "2026-12-31", 45.0, 0.0, 62.00),
            ("bat_azith_001", "prod_azith_500", "AZE25C", "2028-02-28", 15.0, 5.0, 85.00), # low stock
            ("bat_met_001", "prod_met_500", "GLY24D", "2027-05-31", 200.0, 0.0, 24.00),
        ]
        with self.transaction() as conn:
            for bid, pid, bnum, exp, qoh, qres, price in batches:
                conn.execute(
                    """INSERT OR REPLACE INTO inventory_batches
                        (id, product_id, batch_number, expiry_date, quantity_on_hand, quantity_reserved, purchase_price, received_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (bid, pid, bnum, exp, qoh, qres, price, now),
                )

        # Seed Sample Order
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sales_orders
                    (id, buyer_business_id, delivery_address, status, currency, total_amount, items, approved_by, created_at, updated_at)
                   VALUES (?, ?, ?, 'confirmed', 'INR', 1450.0, ?, 'admin_system', ?, ?)""",
                ("ord_lc_1001", b_buyer_id, "Shop 4, MG Road, Camp, Pune 411001",
                 json.dumps([{"product_id": "prod_pcm_500", "qty": 20, "rate": 22.0}]), now, now),
            )

