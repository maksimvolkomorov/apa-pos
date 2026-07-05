import configparser
import os
import sys


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_dir() -> str:
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


_BASE    = _base_dir()
_BUNDLED = _bundled_dir()

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(_BASE, "pos.db")

# ── Defaults ──────────────────────────────────────────────────────────────────
# These are the single source of truth. config.ini overrides them at runtime.
ZEBRA_USB_PATH      = ""   # macOS/Linux only — e.g. "/dev/usb/lp0" (Windows uses ZEBRA_PRINTER_NAME/spooler instead)
ZEBRA_PRINTER_NAME  = ""   # Windows only — exact printer name in "Devices and Printers"; blank = system default printer
ZEBRA_DPI           = 300  # printer resolution — 203 for GX420D/GC420D, 300 for ZD421-300dpi etc.
RECEIPT_WIDTH_IN    = 4.0  # physical width of the loaded receipt paper/label, in inches
BARCODE_WIDTH_IN    = 2.25  # physical width of the loaded barcode label stock, in inches
BARCODE_HEIGHT_IN   = 1.25  # physical height (label pitch) of the loaded gapped barcode label stock, in inches
CURRENCY_SYMBOL     = "$"
TAX_RATE            = 0.0725
PAGE_SIZE           = 20
LOW_STOCK_THRESHOLD = 5
WINDOW_WIDTH        = 1920
WINDOW_HEIGHT       = 1080
RECEIPT_MODE        = "pdf"   # "zebra" | "pdf" | "none"
BARCODE_MODE        = "pdf"   # "zebra" | "pdf" | "none"
STORE_NAME          = "Store name"
STORE_ADDRESS       = [
    "1234 Main Street",
    "City, CA 00000",
    "000-000-0000",
]
ADMIN_PIN           = "1234"
RESET_DB            = False

# ── Derived paths (not overridable) ───────────────────────────────────────────
BARCODE_OUTPUT_DIR = os.path.join(_BASE, "assets", "barcodes")
RECEIPT_OUTPUT_DIR = os.path.join(_BASE, "assets", "receipts")
DB_ARCHIVE_DIR     = os.path.join(_BASE, "db", "archives")

# ── config.ini ────────────────────────────────────────────────────────────────
_INI_PATH = os.path.join(_BASE, "config.ini")


def _write_ini_defaults() -> None:
    """Write current Python defaults to config.ini."""
    cp = configparser.ConfigParser()
    cp["store"] = {
        "name": STORE_NAME,
        "address": "\n" + "\n".join(f"\t{line}" for line in STORE_ADDRESS),
    }
    cp["tax"] = {
        "rate": str(TAX_RATE),
        "currency_symbol": CURRENCY_SYMBOL,
    }
    cp["printer"] = {
        "zebra_dpi":          str(ZEBRA_DPI),
        "receipt_width_in":   str(RECEIPT_WIDTH_IN),
        "barcode_width_in":   str(BARCODE_WIDTH_IN),
        "barcode_height_in":  str(BARCODE_HEIGHT_IN),
        "receipt_mode":       RECEIPT_MODE,
        "barcode_mode":       BARCODE_MODE,
    }
    cp["admin"] = {
        "pin": ADMIN_PIN,
    }
    cp["ui"] = {
        "page_size": str(PAGE_SIZE),
        "low_stock_threshold": str(LOW_STOCK_THRESHOLD),
        "window_width": str(WINDOW_WIDTH),
        "window_height": str(WINDOW_HEIGHT),
    }
    cp["database"] = {
        "reset_db": str(RESET_DB).lower(),
    }
    import io
    buf = io.StringIO()
    cp.write(buf)
    text = buf.getvalue()
    # Zebra USB path/printer name are commented out by default — most
    # deployments print to PDF and only need these once a physical
    # printer is set up.
    text = text.replace(
        "[printer]\n",
        "[printer]\n"
        "# macOS/Linux only — e.g. /dev/usb/lp0 (Windows uses zebra_printer_name/spooler instead)\n"
        "#zebra_usb_path = /dev/usb/lp0\n"
        "# Windows only — exact printer name in \"Devices and Printers\"; blank = system default printer\n"
        f"#zebra_printer_name = {ZEBRA_PRINTER_NAME}\n",
    )
    # Annotate each printer setting with its valid/example values.
    for key, comment in (
        ("zebra_dpi",        "printer resolution — 203 for GX420D/GC420D, 300 for ZD421-300dpi etc."),
        ("receipt_width_in", "physical width of the loaded receipt paper/label, in inches"),
        ("barcode_width_in", "physical width of the loaded barcode label stock, in inches"),
        ("barcode_height_in", "physical height (label pitch) of the loaded gapped barcode label stock, in inches"),
        ("receipt_mode",     "zebra | pdf | none"),
        ("barcode_mode",     "zebra | pdf | none"),
    ):
        text = text.replace(f"{key} = ", f"# {comment}\n{key} = ")
    with open(_INI_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read_ini() -> None:
    """Override Python defaults with values from config.ini."""
    global ZEBRA_USB_PATH, ZEBRA_PRINTER_NAME, ZEBRA_DPI, RECEIPT_WIDTH_IN, BARCODE_WIDTH_IN, BARCODE_HEIGHT_IN, CURRENCY_SYMBOL, TAX_RATE, PAGE_SIZE
    global LOW_STOCK_THRESHOLD, WINDOW_WIDTH, WINDOW_HEIGHT
    global RECEIPT_MODE, BARCODE_MODE, STORE_NAME, STORE_ADDRESS, ADMIN_PIN, RESET_DB

    cp = configparser.ConfigParser()
    cp.read(_INI_PATH, encoding="utf-8")

    if cp.has_option("store", "name"):
        STORE_NAME = cp.get("store", "name")
    if cp.has_option("store", "address"):
        STORE_ADDRESS = [
            line.strip()
            for line in cp.get("store", "address").strip().splitlines()
            if line.strip()
        ]
    if cp.has_option("tax", "rate"):
        TAX_RATE = cp.getfloat("tax", "rate")
    if cp.has_option("tax", "currency_symbol"):
        CURRENCY_SYMBOL = cp.get("tax", "currency_symbol")
    if cp.has_option("printer", "receipt_mode"):
        RECEIPT_MODE = cp.get("printer", "receipt_mode")
    elif cp.has_option("receipt", "mode"):
        RECEIPT_MODE = cp.get("receipt", "mode")
    if cp.has_option("printer", "zebra_usb_path"):
        ZEBRA_USB_PATH = cp.get("printer", "zebra_usb_path")
    if cp.has_option("printer", "zebra_printer_name"):
        ZEBRA_PRINTER_NAME = cp.get("printer", "zebra_printer_name")
    if cp.has_option("printer", "zebra_dpi"):
        ZEBRA_DPI = cp.getint("printer", "zebra_dpi")
    if cp.has_option("printer", "receipt_width_in"):
        RECEIPT_WIDTH_IN = cp.getfloat("printer", "receipt_width_in")
    if cp.has_option("printer", "barcode_width_in"):
        BARCODE_WIDTH_IN = cp.getfloat("printer", "barcode_width_in")
    if cp.has_option("printer", "barcode_height_in"):
        BARCODE_HEIGHT_IN = cp.getfloat("printer", "barcode_height_in")
    if cp.has_option("printer", "barcode_mode"):
        BARCODE_MODE = cp.get("printer", "barcode_mode")
    if cp.has_option("admin", "pin"):
        ADMIN_PIN = cp.get("admin", "pin")
    if cp.has_option("ui", "page_size"):
        PAGE_SIZE = cp.getint("ui", "page_size")
    if cp.has_option("ui", "low_stock_threshold"):
        LOW_STOCK_THRESHOLD = cp.getint("ui", "low_stock_threshold")
    if cp.has_option("ui", "window_width"):
        WINDOW_WIDTH = cp.getint("ui", "window_width")
    if cp.has_option("ui", "window_height"):
        WINDOW_HEIGHT = cp.getint("ui", "window_height")
    if cp.has_option("database", "reset_db"):
        RESET_DB = cp.getboolean("database", "reset_db")


def _load_ini() -> None:
    if not os.path.exists(_INI_PATH):
        _write_ini_defaults()
    _read_ini()


_load_ini()
