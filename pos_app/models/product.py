import sqlite3
import uuid

from db.database import get_connection


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def _make_barcode(product_id: int) -> str:
    return f"APA{product_id:06d}"


# ── Queries ───────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    rows = get_connection().execute(
        "SELECT * FROM products ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [_row(r) for r in rows]


def search(query: str) -> list[dict]:
    q = f"%{query}%"
    rows = get_connection().execute(
        "SELECT * FROM products"
        " WHERE name LIKE ? OR barcode LIKE ?"
        " ORDER BY name COLLATE NOCASE",
        (q, q),
    ).fetchall()
    return [_row(r) for r in rows]


def get_by_id(product_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    return _row(row) if row else None


def get_by_barcode(barcode: str) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM products WHERE barcode = ?", (barcode,)
    ).fetchone()
    return _row(row) if row else None


# ── Mutations ─────────────────────────────────────────────────────────────────

def create(name: str, stock: int, price: float) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    # Use a unique temp barcode so the NOT NULL / UNIQUE constraint holds
    # until we know the real auto-assigned id.
    temp = f"__pending_{uuid.uuid4().hex}"
    cur.execute(
        "INSERT INTO products (name, barcode, stock, price) VALUES (?, ?, ?, ?)",
        (name, temp, stock, price),
    )
    product_id = cur.lastrowid
    barcode = _make_barcode(product_id)
    cur.execute(
        "UPDATE products SET barcode = ? WHERE id = ?", (barcode, product_id)
    )
    conn.commit()
    return get_by_id(product_id)


def update(product_id: int, name: str, stock: int, price: float) -> dict:
    conn = get_connection()
    conn.execute(
        "UPDATE products SET name = ?, stock = ?, price = ? WHERE id = ?",
        (name, stock, price, product_id),
    )
    conn.commit()
    return get_by_id(product_id)


def update_stock(product_id: int, delta: int) -> None:
    """Apply delta (negative to decrement) to a product's stock."""
    conn = get_connection()
    conn.execute(
        "UPDATE products SET stock = stock + ? WHERE id = ?",
        (delta, product_id),
    )
    conn.commit()


def delete(product_id: int) -> bool:
    """
    Delete a product.  order_items.product_id is set to NULL automatically
    via ON DELETE SET NULL — order history is preserved through the
    snapshotted product_name column.
    """
    conn = get_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    return True
