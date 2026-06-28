"""Zebra GX420D service — ZPL builder and USB sender.

All functions are pure Python; no external dependencies required.
"""
import os
import sys

import config


def build_product_zpl(title: str, barcode: str) -> str:
    """
    Build a ZPL label for the Zebra GX420D on 4" (812-dot @ 203 DPI) paper.

    Layout (approx 1.5" / 305 dots tall):
      - Product title — top, large scalable font
      - Code128 bars  — middle
      - Human-readable barcode string — printed by ^BC automatically
    """
    display_name = title if len(title) <= 28 else title[:25] + "…"

    return (
        "^XA\n"
        "^MNN\n"             # non-continuous media (gap/web sensing) for label stock
        "^PW812\n"           # print width: 4 in = 812 dots
        "^LL305\n"           # label length: ~1.5 in = 305 dots
        "^CI28\n"            # UTF-8 encoding
        f"^FO30,18^A0N,38,38^FD{display_name}^FS\n"   # name
        f"^FO30,72^BCN,100,Y,N,N^FD{barcode}^FS\n"    # Code128, 100-dot bars, human-readable
        "^XZ\n"
    )


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
