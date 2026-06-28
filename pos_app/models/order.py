import sqlite3
from datetime import datetime

from db.database import get_connection


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Queries ───────────────────────────────────────────────────────────────────

def get_all(date_from: str = None, date_to: str = None) -> list[dict]:
    """Return orders newest-first, optionally filtered by date (YYYY-MM-DD)."""
    clauses, params = [], []
    if date_from:
        clauses.append("DATE(created_at) >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("DATE(created_at) <= ?")
        params.append(date_to)

    sql = "SELECT * FROM orders"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC, id DESC"

    rows = get_connection().execute(sql, params).fetchall()
    return [_row(r) for r in rows]


def get_by_id(order_id: int) -> dict | None:
    row = get_connection().execute(
        "SELECT * FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    return _row(row) if row else None


def get_items(order_id: int) -> list[dict]:
    """Return order_items for a given order using the snapshotted product_name."""
    rows = get_connection().execute(
        """
        SELECT id, order_id, product_id, product_name, quantity, unit_price
        FROM order_items
        WHERE order_id = ?
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def item_count(order_id: int) -> int:
    row = get_connection().execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    return row[0]


# ── Mutations ─────────────────────────────────────────────────────────────────

def create(items: list[dict], processed_by: str | None = None,
           discount_pct: float = 0.0, payment_method: str = "cash",
           customer_name: str | None = None) -> dict:
    """
    Create an order and atomically decrement stock.

    items: [{"product_id": int, "quantity": int, "unit_price": float}, ...]

    Returns the new order dict.
    Raises ValueError if any item has insufficient stock.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Pre-flight: validate stock and snapshot product names
    product_names: dict[int, str] = {}
    for item in items:
        row = cur.execute(
            "SELECT stock, title FROM products WHERE id = ?", (item["product_id"],)
        ).fetchone()
        if row is None:
            raise ValueError(f"Product id={item['product_id']} not found.")
        if row["stock"] < item["quantity"]:
            raise ValueError(
                f"Insufficient stock for '{row['title']}': "
                f"have {row['stock']}, need {item['quantity']}."
            )
        product_names[item["product_id"]] = row["title"]

    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    if payment_method == "gift":
        discount_pct, total = 0.0, 0.0
    else:
        discount_pct = max(0.0, min(100.0, float(discount_pct)))
        total = round(subtotal * (1 - discount_pct / 100), 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with conn:
        cur.execute(
            "INSERT INTO orders"
            " (total, discount_pct, payment_method, customer_name, processed_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (total, discount_pct, payment_method,
             customer_name or None, processed_by or None, now),
        )
        order_id = cur.lastrowid
        for item in items:
            cur.execute(
                "INSERT INTO order_items"
                " (order_id, product_id, product_name, quantity, unit_price)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    order_id,
                    item["product_id"],
                    product_names[item["product_id"]],
                    item["quantity"],
                    item["unit_price"],
                ),
            )
            cur.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (item["quantity"], item["product_id"]),
            )

    return get_by_id(order_id)
