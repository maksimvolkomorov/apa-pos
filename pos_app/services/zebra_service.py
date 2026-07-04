"""Zebra GX420D service — ZPL builder and USB sender.

All functions are pure Python; no external dependencies required.
"""
import os
import sys

import config


def _wrap_name(title: str, max_chars: int) -> list[str]:
    """Word-wrap title into at most 2 lines of max_chars; truncate with '...'."""
    upper = title.upper().strip()
    if len(upper) <= max_chars:
        return [upper]
    words = upper.split()
    line1: list[str] = []
    for word in words:
        if len(" ".join(line1 + [word])) <= max_chars:
            line1.append(word)
        else:
            break
    l1 = " ".join(line1)
    l2 = " ".join(words[len(line1):])
    if not l1:
        return [upper[:max_chars - 3] + "..."]
    if not l2:
        return [l1]
    if len(l2) <= max_chars:
        return [l1, l2]
    return [l1, l2[:max_chars - 3] + "..."]


def build_product_zpl(title: str, barcode: str, price: float | None = None) -> str:
    """
    Build a ZPL label for the Zebra GX420D on 4" (812-dot @ 203 DPI) paper.

    Layout (dynamic height):
      - Product title — up to 2 lines, top
      - Price         — below title (when provided)
      - Code128 bars  — middle, with human-readable text
    """
    name_lines = _wrap_name(title, 28)
    price_line = f"{config.CURRENCY_SYMBOL}{price:.2f}" if price is not None else ""

    font_h    = 30
    pitch     = 36   # dots per name line
    zpl_lines = ["^XA", "^MNN", "^PW812", "^CI28"]

    y = 15
    for nl in name_lines:
        zpl_lines.append(f"^FO30,{y}^A0N,{font_h},{font_h}^FD{nl}^FS")
        y += pitch

    price_y   = y + 4
    barcode_y = price_y + 34
    label_h   = barcode_y + 130   # 100-dot bars + human-readable + bottom margin

    zpl_lines.append(f"^LL{label_h}")
    zpl_lines.append(f"^FO30,{price_y}^A0N,26,26^FD{price_line}^FS")
    zpl_lines.append(f"^FO30,{barcode_y}^BCN,100,Y,N,N^FD{barcode}^FS")
    zpl_lines.append("^XZ")
    return "\n".join(zpl_lines) + "\n"


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
