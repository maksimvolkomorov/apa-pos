"""Zebra printer service — shared ZPL/image helpers and USB/spooler sender.

Used by both barcode_service.py (product labels) and receipt_service.py
(receipts) — anything specific to one or the other lives in that module
instead.
"""
import os
import sys

import config


def find_ttf_fonts() -> tuple[str | None, str | None]:
    """Locate a Unicode-capable (regular, bold) TTF pair for PIL rendering."""
    candidates = [
        ("C:/Windows/Fonts/arial.ttf",   "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("/Library/Fonts/Arial.ttf",     "/Library/Fonts/Arial Bold.ttf"),
    ]
    for reg, bold in candidates:
        if os.path.exists(reg) and os.path.exists(bold):
            return reg, bold
    return None, None


def image_to_zpl_gf(img) -> tuple[str, int, int]:
    """
    Convert a Pillow image to a ZPL ^GFA graphic-field command.

    Returns (gf_command, width_px, height_px). ZPL's bit convention is
    1 = black/print, 0 = white — the inverse of PIL's packed mode "1"
    (1 = white), so the packed bytes are bitwise-inverted before encoding.
    """
    from PIL import Image
    bw = img.convert("L").convert("1", dither=Image.NONE)
    w, h = bw.size
    bytes_per_row = (w + 7) // 8
    packed = bw.tobytes()
    inverted = bytes(b ^ 0xFF for b in packed)
    hex_data = inverted.hex().upper()
    total_bytes = len(inverted)
    cmd = f"^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}"
    return cmd, w, h


def _print_raw_windows(data: bytes, printer_name: str | None) -> None:
    r"""
    Send raw bytes to a Windows printer via the print spooler (RAW datatype).

    Modern Windows locks \\.\USBxxx ports to the spooler service, so a plain
    open()/CreateFile from user code no longer works — this goes through
    win32print instead, which is the supported path regardless of whether
    the printer is on USB, network, or WSD.

    Raises OSError on failure (mirrors the old file-based API for callers).
    """
    try:
        import win32print
    except ImportError as exc:
        raise OSError("pywin32 is required for Windows printing (pip install pywin32)") from exc

    name = printer_name or config.ZEBRA_PRINTER_NAME or win32print.GetDefaultPrinter()

    try:
        handle = win32print.OpenPrinter(name)
    except Exception as exc:
        raise OSError(f"Could not open printer '{name}': {exc}") from exc

    try:
        job_id = win32print.StartDocPrinter(handle, 1, ("ZPL Label", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    except Exception as exc:
        raise OSError(f"Print job to '{name}' failed: {exc}") from exc
    finally:
        win32print.ClosePrinter(handle)


def print_label_usb(zpl: str, usb_path: str | None = None) -> None:
    r"""
    Send ZPL to the Zebra printer.

    Windows : sent via the print spooler (config.ZEBRA_PRINTER_NAME, or the
              Windows default printer if unset).
    macOS   : written directly to the USB device path, e.g. '/dev/usb/lp0'.

    Raises OSError if the print job cannot be sent.
    """
    if sys.platform == "win32":
        _print_raw_windows(zpl.encode("utf-8"), None)
        return

    path = usb_path or config.ZEBRA_USB_PATH
    if not path:
        raise ValueError(
            "No USB printer path configured. "
            "Set ZEBRA_USB_PATH in config.py."
        )
    with open(path, "wb") as fh:
        fh.write(zpl.encode("utf-8"))


def printer_available(usb_path: str | None = None) -> bool:
    """Return True if the printer can be opened for writing."""
    if sys.platform == "win32":
        try:
            import win32print
            name = config.ZEBRA_PRINTER_NAME or win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(name)
            win32print.ClosePrinter(handle)
            return True
        except Exception:
            return False

    path = usb_path or config.ZEBRA_USB_PATH
    if not path:
        return False
    try:
        with open(path, "wb") as fh:
            fh.write(b"")
        return True
    except OSError:
        return False
