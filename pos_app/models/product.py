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
        "SELECT * FROM products ORDER BY title COLLATE NOCASE"
    ).fetchall()
    return [_row(r) for r in rows]


def search(query: str) -> list[dict]:
    q = f"%{query}%"
    rows = get_connection().execute(
        "SELECT * FROM products"
        " WHERE title LIKE ? OR author LIKE ? OR barcode LIKE ?"
        " ORDER BY title COLLATE NOCASE",
        (q, q, q),
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

def create(title: str, stock: int, price: float, *,
           author: str = "", publisher: str = "",
           webstore: str = "", location: str = "",
           storage: int | None = None) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    temp = f"__pending_{uuid.uuid4().hex}"
    cur.execute(
        "INSERT INTO products"
        " (title, author, publisher, webstore, location, storage, barcode, stock, price)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, author or None, publisher or None,
         webstore or None, location or None, storage, temp, stock, price),
    )
    product_id = cur.lastrowid
    barcode = _make_barcode(product_id)
    cur.execute("UPDATE products SET barcode = ? WHERE id = ?", (barcode, product_id))
    conn.commit()
    return get_by_id(product_id)


def update(product_id: int, title: str, stock: int, price: float, *,
           author: str = "", publisher: str = "",
           webstore: str = "", location: str = "",
           storage: int | None = None) -> dict:
    conn = get_connection()
    conn.execute(
        "UPDATE products"
        " SET title=?, author=?, publisher=?, webstore=?, location=?, storage=?,"
        "     stock=?, price=?"
        " WHERE id=?",
        (title, author or None, publisher or None,
         webstore or None, location or None, storage, stock, price, product_id),
    )
    conn.commit()
    return get_by_id(product_id)


def update_stock(product_id: int, delta: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE products SET stock = stock + ? WHERE id = ?",
        (delta, product_id),
    )
    conn.commit()


def delete(product_id: int) -> bool:
    conn = get_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    return True
