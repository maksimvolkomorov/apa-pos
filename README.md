# APA@POS

Point of Sale application for St. Herman Monastery. Built with Python + Tkinter + SQLite. Runs on Windows (primary) and macOS.

## Features

- Product catalog with barcode generation (Code128)
- POS screen with barcode scan and name autocomplete
- Order history with date filtering
- Receipt printing via Zebra ZPL, PDF, or none
- Import/Export (xlsx)
- User tracking

## Local Setup

**Requirements:** Python 3.12+, Tkinter (included with python.org installer on Windows; `brew install python-tk@3.12` on macOS)

```bash
cd pos_app
pip install -r requirements.txt
python main.py
```

Seed with sample data (optional):

```bash
python seed.py
```

## Configuration

Edit `pos_app/config.py` to set:

| Variable | Purpose |
|---|---|
| `ZEBRA_USB_PATH` | USB path to Zebra printer (`r"\\.\USB001"` on Windows, `/dev/usb/lp0` on macOS) |
| `TAX_RATE` | Decimal tax rate (e.g. `0.07` for 7%) |
| `RECEIPT_MODE` | `"zebra"`, `"pdf"`, or `"none"` |
| `STORE_NAME` / `STORE_ADDRESS` | Printed on receipts |

## Building (Windows)

```powershell
cd pos_app
pip install pyinstaller
python -c "from PIL import Image; img = Image.open('assets/apa-app-logo.png'); img.save('assets/apa-app-logo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
pyinstaller build_windows.spec
```

Output: `dist\APA_POS\` — distribute the entire folder as a zip.

Releases are also built automatically via GitHub Actions (`workflow_dispatch` with a version input).
