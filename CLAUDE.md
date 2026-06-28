# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

APA@POS is a desktop Point of Sale application for St. Herman Monastery. Built with Python + Tkinter + SQLite. Targets Windows (primary) and macOS. Distributed as a PyInstaller bundle.

## Running the App

```bash
cd pos_app
pip install -r requirements.txt
py main.py
```

Seed the database with sample products and orders:
```bash
cd pos_app
py seed.py
```

## Building for Windows

The Windows build is triggered manually via GitHub Actions (`workflow_dispatch`) with a version input (e.g. `v1.0.0`). It runs `pyinstaller build_windows.spec` and produces `dist\APA_POS\APA_POS.exe`, zips the folder, and creates a GitHub Release.

To build locally on Windows:
```powershell
cd pos_app
pip install pyinstaller
# Convert PNG to ICO first (Pillow required):
py -c "from PIL import Image; img = Image.open('assets/apa-app-logo.png'); img.save('assets/apa-app-logo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
pyinstaller build_windows.spec
```

Output: `dist\APA_POS\APA_POS.exe` — distribute the entire `dist\APA_POS\` folder as a zip.

## Architecture

### Module Layout

```
pos_app/
├── main.py          # Entry point — DPI awareness, DB init, launches App
├── config.py        # All runtime config (DB path, printer path, tax rate, etc.)
├── seed.py          # Dev-only: wipes and repopulates the DB with sample data
├── db/
│   ├── database.py  # Singleton connection, migrations, DB reset logic
│   └── schema.sql   # Initial schema (run via executescript on startup)
├── models/
│   ├── product.py   # Product CRUD
│   └── order.py     # Order + OrderItem CRUD
├── services/
│   ├── barcode_service.py  # Generates Code128 barcode string + PNG file
│   ├── zebra_service.py    # Builds ZPL and writes bytes to USB printer path
│   └── receipt_service.py  # Dispatches receipts (Zebra ZPL / PDF / none)
└── ui/
    ├── app.py          # Root Tk window (1024×768), nav bar, tab switching
    ├── theme.py        # Colours, fonts, shared widget styles
    ├── stock_view.py   # Stock management: CRUD, search, pagination, barcode print
    ├── pos_view.py     # POS screen: barcode scan, name autocomplete, checkout
    └── history_view.py # Order history: date filter, pagination, detail modal
```

### Key Design Decisions

**Single SQLite connection** — `db/database.py` keeps one module-level connection (`_conn`) with `check_same_thread=False`. All models import `get_connection()` directly; there is no ORM or connection pool.

**Schema migrations run on every startup** — `_migrate()` calls `executescript(schema.sql)` (which uses `CREATE TABLE IF NOT EXISTS`) then applies named Python migration functions. Add new migrations as `_migrate_<name>(conn)` functions called from `_migrate()`.

**PyInstaller path split** — `config.py` distinguishes two base directories: `_BASE` (executable directory, writable — DB, receipts, barcodes) and `_BUNDLED` (`sys._MEIPASS` when frozen, writable source dir otherwise — schema.sql, logo). Use `_BUNDLED` for read-only bundled assets and `_BASE` for user-writable outputs.

**DB reset via config flag** — Setting `RESET_DB = True` in `config.py` causes `database.py` to archive the existing `.db` file to `db/archives/` on next launch and rewrite the flag back to `False` in `config.py` automatically.

**Barcode format** — Auto-generated on product creation: `APA` + zero-padded product ID (e.g. `APA000001`). Stored in `products.barcode`. Never entered by users.

**order_items schema (v2)** — `order_items` stores a `product_name` snapshot so order history survives product deletion. `product_id` is nullable (`ON DELETE SET NULL`). The v2 migration in `database.py` handles upgrading existing DBs transparently.

## Configuration (`config.py`)

All deployment-specific values live here. Key settings:

| Variable | Purpose |
|---|---|
| `ZEBRA_USB_PATH` | USB path to Zebra printer: `r"\\.\USB001"` (Windows) or `/dev/usb/lp0` (macOS) |
| `TAX_RATE` | Decimal tax rate (e.g. `0.07` for 7%) |
| `RECEIPT_MODE` | `"zebra"`, `"pdf"`, or `"none"` |
| `STORE_NAME` / `STORE_ADDRESS` | Appears on receipts |
| `RESET_DB` | Set `True` once to archive DB and start fresh |

## Platform Notes

- Windows: use `r"\\.\USB001"` or `r"\\.\COM3"` for Zebra (check Device Manager). Python from python.org includes Tk.
- macOS: `config.py` USB path → `/dev/usb/lp0`. Must install `brew install python-tk@3.12`.
- Only `config.py` differs between platforms.
