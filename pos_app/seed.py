"""
Seed script — populates pos.db with Russian literature titles.
Run from pos_app/:  python3 seed.py
Safe to re-run: clears existing data first.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import get_connection
from models import product as pm, order as om
from datetime import datetime, timedelta

# ── Wipe ──────────────────────────────────────────────────────────────────────
conn = get_connection()
conn.executescript(
    "DELETE FROM order_items;"
    "DELETE FROM orders;"
    "DELETE FROM products;"
    "DELETE FROM sqlite_sequence;"
)
conn.commit()
print("Database cleared.")

# ── Products — Russian literature ─────────────────────────────────────────────
# (title, price, stock)
PRODUCTS = [
    # Tolstoy
    ("War and Peace",                          24.99, 45),
    ("Anna Karenina",                          18.99, 60),
    ("The Death of Ivan Ilyich",               12.99, 38),
    ("Resurrection",                           17.99, 30),
    # Dostoevsky
    ("Crime and Punishment",                   16.99, 55),
    ("The Brothers Karamazov",                 22.99, 40),
    ("The Idiot",                              17.99, 35),
    ("Demons",                                 18.99, 32),
    ("Notes from Underground",                 11.99, 42),
    ("The Gambler",                            12.99, 28),
    # Chekhov
    ("The Cherry Orchard",                     12.99, 50),
    ("Three Sisters",                          11.99, 45),
    ("The Seagull",                            11.99, 35),
    ("Uncle Vanya",                            11.99, 30),
    ("Ward No. 6",                             10.99, 25),
    # Turgenev
    ("Fathers and Sons",                       14.99, 38),
    ("First Love",                             10.99, 45),
    ("Rudin",                                  12.99, 22),
    ("On the Eve",                             13.99, 20),
    # Gogol
    ("Dead Souls",                             15.99, 42),
    ("The Overcoat",                           10.99, 30),
    ("Taras Bulba",                            13.99, 28),
    # Bulgakov
    ("The Master and Margarita",               19.99, 70),
    ("Heart of a Dog",                         13.99, 55),
    # Pushkin
    ("Eugene Onegin",                          13.99, 65),
    ("The Captain's Daughter",                 12.99, 35),
    # Others
    ("Doctor Zhivago",                         21.99, 48),   # Pasternak
    ("A Hero of Our Time",                     14.99, 42),   # Lermontov
    ("Oblomov",                                16.99, 25),   # Goncharov
    ("One Day in the Life of Ivan Denisovich",  0.00,  0),   # Solzhenitsyn — out of stock demo
]

created = []
for name, price, stock in PRODUCTS:
    p = pm.create(name, stock=stock, price=price)
    created.append(p)
    flag = "⚠" if stock == 0 else " "
    print(f"  {flag} {p['barcode']}  {p['name']:<42}  ${p['price']:.2f}  stock={p['stock']}")

print(f"\n{len(created)} products created.")

# ── Orders — 25 orders across the last 14 days ────────────────────────────────
random.seed(99)
cur         = conn.cursor()
base_date   = datetime.now()
order_count = 0
in_stock    = [p for p in created if p["stock"] > 0]

for days_ago in range(13, -1, -1):
    for _ in range(random.randint(1, 3)):
        ts = (base_date - timedelta(days=days_ago)).replace(
            hour   = random.randint(9, 20),
            minute = random.randint(0, 59),
            second = 0, microsecond=0,
        ).strftime("%Y-%m-%d %H:%M:%S")

        picks      = random.sample(in_stock, random.randint(1, 4))
        subtotal   = 0.0
        line_items = []
        for p in picks:
            qty       = random.randint(1, 3)
            subtotal += qty * p["price"]
            line_items.append((p["id"], p["name"], qty, p["price"]))

        cur.execute(
            "INSERT INTO orders (total, created_at) VALUES (?, ?)",
            (round(subtotal, 2), ts),
        )
        oid = cur.lastrowid
        for pid, pname, qty, uprice in line_items:
            cur.execute(
                "INSERT INTO order_items"
                " (order_id, product_id, product_name, quantity, unit_price)"
                " VALUES (?, ?, ?, ?, ?)",
                (oid, pid, pname, qty, uprice),
            )
            cur.execute(
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                (qty, pid),
            )
        conn.commit()
        order_count += 1
        print(f"  Order #{oid:>2}  {ts}  {len(line_items)} item(s)  ${subtotal:.2f}")

print(f"\n{order_count} orders created.")
print("\nSeed complete. Run the app: python3 main.py")
