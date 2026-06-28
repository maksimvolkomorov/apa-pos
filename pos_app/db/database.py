import os
import re
import shutil
import sqlite3
from datetime import datetime

import config

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if config.RESET_DB:
            _reset_database()
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
        _migrate(_conn)
    return _conn


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


# ── Reset ─────────────────────────────────────────────────────────────────────

def _reset_database() -> None:
    """Archive the existing DB file, then rewrite config.py to set RESET_DB = False."""
    if os.path.exists(config.DB_PATH):
        os.makedirs(config.DB_ARCHIVE_DIR, exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive  = os.path.join(config.DB_ARCHIVE_DIR, f"pos_{ts}.db")
        shutil.move(config.DB_PATH, archive)

        # Also move the WAL/SHM sidecar files if present
        for ext in ("-wal", "-shm"):
            src = config.DB_PATH + ext
            if os.path.exists(src):
                shutil.move(src, archive + ext)

    _toggle_reset_flag(False)


def _toggle_reset_flag(value: bool) -> None:
    """Rewrite the RESET_DB line in config.py."""
    config_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "config.py")
    )
    with open(config_path, encoding="utf-8") as fh:
        src = fh.read()

    new_src = re.sub(
        r"^RESET_DB\s*=\s*(True|False)",
        f"RESET_DB = {value}",
        src,
        flags=re.MULTILINE,
    )

    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(new_src)

    # Keep the in-process config in sync
    config.RESET_DB = value


def _migrate(conn: sqlite3.Connection) -> None:
    schema_path = os.path.join(config._BUNDLED, "db", "schema.sql")
    with open(schema_path, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    _migrate_order_items_snapshot(conn)
    _migrate_products_v3(conn)
    _migrate_products_v4(conn)


def _migrate_products_v3(conn: sqlite3.Connection) -> None:
    """
    v3 migration: rename name→title, add author/publisher/webstore/location.
    Safe to run on every startup — no-op if already migrated.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    if "name" in cols:
        conn.execute("ALTER TABLE products RENAME COLUMN name TO title")
        conn.commit()
        cols.add("title")
        cols.discard("name")
    for col in ("author", "publisher", "webstore", "location"):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
    conn.commit()


def _migrate_products_v4(conn: sqlite3.Connection) -> None:
    """v4 migration: add storage (INTEGER) column."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    if "storage" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN storage INTEGER")
        conn.commit()


def _migrate_order_items_snapshot(conn: sqlite3.Connection) -> None:
    """
    v2 migration: add product_name snapshot column to order_items and
    make product_id nullable (ON DELETE SET NULL).

    Safe to run on every startup — no-op if already migrated.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(order_items)")}
    if "product_name" in cols:
        return

    conn.executescript("""
        CREATE TABLE order_items_v2 (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id     INTEGER NOT NULL REFERENCES orders(id),
            product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
            product_name TEXT    NOT NULL,
            quantity     INTEGER NOT NULL,
            unit_price   REAL    NOT NULL
        );

        INSERT INTO order_items_v2
            (id, order_id, product_id, product_name, quantity, unit_price)
        SELECT
            oi.id,
            oi.order_id,
            oi.product_id,
            COALESCE(p.name, 'Unknown Product'),
            oi.quantity,
            oi.unit_price
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id;

        DROP TABLE order_items;
        ALTER TABLE order_items_v2 RENAME TO order_items;

        CREATE INDEX IF NOT EXISTS idx_order_items_order
            ON order_items(order_id);
    """)
