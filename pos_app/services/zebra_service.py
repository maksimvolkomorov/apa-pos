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


def print_label_usb(zpl: str, usb_path: str | None = None) -> None:
    r"""
    Write ZPL bytes directly to the Zebra printer via USB.

    usb_path examples:
      Windows : r'\\.\USB001'  (check Device Manager)
      macOS   : '/dev/usb/lp0'

    Raises OSError if the printer path cannot be opened.
    """
    path = usb_path or config.ZEBRA_USB_PATH
    if not path:
        raise ValueError(
            "No USB printer path configured. "
            "Set ZEBRA_USB_PATH in config.py."
        )

    # On Windows, opening the raw port name requires the \\.\  prefix.
    # The open() call works the same on both platforms.
    with open(path, "wb") as fh:
        fh.write(zpl.encode("utf-8"))


def printer_available(usb_path: str | None = None) -> bool:
    """Return True if the printer path exists and can be opened for writing."""
    path = usb_path or config.ZEBRA_USB_PATH
    if not path:
        return False
    try:
        # On Windows, just checking os.path.exists() is not reliable for
        # device paths; attempt a zero-byte write instead.
        with open(path, "wb") as fh:
            fh.write(b"")
        return True
    except OSError:
        return False
