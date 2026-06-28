import sqlite3
from db.database import get_connection


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


def get_all() -> list[dict]:
    rows = get_connection().execute(
        "SELECT * FROM users ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [_row(r) for r in rows]


def create(name: str) -> dict:
    conn = get_connection()
    conn.execute("INSERT INTO users (name) VALUES (?)", (name.strip(),))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE name = ?", (name.strip(),)).fetchone()
    return _row(row)


def delete(user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
