import os
import sys


def _base_dir() -> str:
    """Return the base directory for resolving asset and DB paths.

    When running from source: the pos_app/ folder.
    When bundled with PyInstaller: sys._MEIPASS (extracted bundle temp dir)
    for read-only bundled files, but the executable's directory for
    writable files (DB, receipts, barcodes).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_dir() -> str:
    """Read-only assets bundled inside the PyInstaller package."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


_BASE    = _base_dir()
_BUNDLED = _bundled_dir()

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(_BASE, "pos.db")

# ── Zebra GX420D — USB only ───────────────────────────────────────────────────
# Windows: r"\\.\USB001"  (check Device Manager for the exact port)
# macOS:   "/dev/usb/lp0"
ZEBRA_USB_PATH = r"\\.\USB001"

# ── Currency & Tax ────────────────────────────────────────────────────────────
CURRENCY_SYMBOL = "$"
TAX_RATE        = 0.07        # e.g. 0.10 for 10 %

# ── UI ────────────────────────────────────────────────────────────────────────
PAGE_SIZE = 15               # rows per page in tables

# ── Barcode output ────────────────────────────────────────────────────────────
BARCODE_OUTPUT_DIR = os.path.join(_BASE, "assets", "barcodes")

# ── Receipt on checkout ───────────────────────────────────────────────────────
# "zebra"  — print ZPL receipt to the Zebra GX420D via USB
# "pdf"    — save a PDF (or .txt fallback) to RECEIPT_OUTPUT_DIR and open it
# "none"   — no receipt
RECEIPT_MODE       = "pdf"
RECEIPT_OUTPUT_DIR = os.path.join(_BASE, "assets", "receipts")

# ── Receipt header ────────────────────────────────────────────────────────────
STORE_NAME    = "St. Herman Monastery"
STORE_ADDRESS = [
    "123 Main Street",
    "City, ST 00000",
    "Tel: (000) 000-0000",
]

# ── Database reset ────────────────────────────────────────────────────────────
# Set to True to archive the current database and start fresh on next launch.
# The app will automatically reset this back to False after the reset completes.
RESET_DB       = False
DB_ARCHIVE_DIR = os.path.join(_BASE, "db", "archives")

