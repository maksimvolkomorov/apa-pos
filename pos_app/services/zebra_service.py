"""Zebra GX420D service — ZPL builder and USB sender.

Labels/receipts are rendered as bitmaps (Pillow) and embedded via ZPL's
^GF graphic field when Pillow is available — this sidesteps ^A0N's
proportional-font alignment quirks and ^BY's 10-dot module-width cap,
using real font metrics and pixel-exact bar widths instead. Falls back
to composing plain ZPL field commands when Pillow isn't installed.
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


# ── Physical label layout ─────────────────────────────────────────────────────
# Original design was tuned for a 203 DPI printer; these constants preserve
# the same physical (inch) proportions at any config.ZEBRA_DPI, and widen the
# barcode module so the bars scale up to use the label's full width.
_BC_MARGIN_IN     = 0.148   # 30/203
_BC_TITLE_SIZE_IN = 0.148   # 30/203
_BC_PRICE_SIZE_IN = 0.128   # 26/203
_BC_PITCH_IN      = 0.177   # 36/203
_BC_BAR_HEIGHT_IN = 0.493   # 100/203
_BC_MODULE        = 10      # bar (module) width in dots — Zebra firmware caps ^BY's w at 10

_BC_SCALE      = config.ZEBRA_DPI / 203
_BC_MARGIN     = round(_BC_MARGIN_IN     * config.ZEBRA_DPI)
_BC_TITLE_H    = round(_BC_TITLE_SIZE_IN * config.ZEBRA_DPI)
_BC_PRICE_H    = round(_BC_PRICE_SIZE_IN * config.ZEBRA_DPI)
_BC_PITCH      = round(_BC_PITCH_IN      * config.ZEBRA_DPI)
_BC_BAR_HEIGHT = round(_BC_BAR_HEIGHT_IN * config.ZEBRA_DPI)
_BC_WIDTH_DOTS = round(config.RECEIPT_WIDTH_IN * config.ZEBRA_DPI)


def build_product_zpl(title: str, barcode: str, price: float | None = None) -> str:
    """
    Build a ZPL barcode label for the Zebra printer on 4" continuous paper.

    Renders the label as a bitmap (Pillow) and embeds it via ^GF — draws
    the Code128 bars directly at whatever width we choose, with no ^BY
    10-dot firmware cap. Falls back to plain ZPL field commands (native
    ^BCN barcode, capped bar width) if Pillow isn't installed.
    """
    try:
        return _build_product_zpl_image(title, barcode, price)
    except ImportError:
        return _build_product_zpl_fields(title, barcode, price)


def _build_product_zpl_image(title: str, barcode: str, price: float | None) -> str:
    from PIL import Image, ImageDraw, ImageFont

    name_lines = _wrap_name(title, 28)
    price_line = f"{config.CURRENCY_SYMBOL}{price:.2f}" if price is not None else ""

    reg_path, bold_path = find_ttf_fonts()

    def font(size: int, bold: bool = False):
        path = (bold_path or reg_path) if bold else reg_path
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()

    f_title = font(_BC_TITLE_H, bold=True)
    f_price = font(_BC_PRICE_H)
    f_num   = font(round(_BC_PRICE_H * 0.85))

    width = _BC_WIDTH_DOTS
    img   = Image.new("L", (width, 2000), 255)   # generous height; cropped below
    draw  = ImageDraw.Draw(img)

    y = round(15 * _BC_SCALE)
    for nl in name_lines:
        draw.text((_BC_MARGIN, y), nl, font=f_title, fill=0)
        y += _BC_PITCH

    if price_line:
        y += round(4 * _BC_SCALE)
        draw.text((_BC_MARGIN, y), price_line, font=f_price, fill=0)
    y += round(38 * _BC_SCALE)

    # Code128 bars, drawn at an explicit target width — no firmware cap.
    from services.barcode_service import _bar_units
    bars       = _bar_units(barcode)
    total_units = sum(u for _, u in bars)
    max_bar_w  = 0.75 * (width - _BC_MARGIN * 2)
    scale      = max_bar_w / total_units

    cx = _BC_MARGIN
    bar_top = y
    for is_black, units in bars:
        w = units * scale
        if is_black:
            draw.rectangle([cx, bar_top, cx + w, bar_top + _BC_BAR_HEIGHT], fill=0)
        cx += w
    y = bar_top + _BC_BAR_HEIGHT + round(6 * _BC_SCALE)

    num_w = draw.textlength(barcode, font=f_num)
    draw.text(((width - num_w) / 2, y), barcode, font=f_num, fill=0)
    y += round(_BC_PRICE_H * 0.85) + round(15 * _BC_SCALE)

    cropped = img.crop((0, 0, width, y))
    gf_cmd, gw, gh = image_to_zpl_gf(cropped)

    header = f"^XA\n^MNN\n^PW{width}\n^LL{gh}\n^CI28\n"
    return header + f"^FO0,0{gf_cmd}^FS\n^XZ\n"


def _build_product_zpl_fields(title: str, barcode: str, price: float | None = None) -> str:
    """Fallback ZPL builder using native ^BCN (no Pillow required; bar width capped at ^BY's max of 10)."""
    name_lines = _wrap_name(title, 28)
    price_line = f"{config.CURRENCY_SYMBOL}{price:.2f}" if price is not None else ""

    zpl_lines = ["^XA", "^MNN", f"^PW{_BC_WIDTH_DOTS}", "^CI28"]

    y = round(15 * _BC_SCALE)
    for nl in name_lines:
        zpl_lines.append(f"^FO{_BC_MARGIN},{y}^A0N,{_BC_TITLE_H},{_BC_TITLE_H}^FD{nl}^FS")
        y += _BC_PITCH

    price_y   = y + round(4 * _BC_SCALE)
    barcode_y = price_y + round(34 * _BC_SCALE)
    label_h   = barcode_y + _BC_BAR_HEIGHT + round(30 * _BC_SCALE)   # bars + human-readable text + bottom margin

    zpl_lines.append(f"^LL{label_h}")
    zpl_lines.append(f"^FO{_BC_MARGIN},{price_y}^A0N,{_BC_PRICE_H},{_BC_PRICE_H}^FD{price_line}^FS")
    zpl_lines.append(f"^BY{_BC_MODULE},2,{_BC_BAR_HEIGHT}")
    zpl_lines.append(f"^FO{_BC_MARGIN},{barcode_y}^BCN,{_BC_BAR_HEIGHT},Y,N,N^FD{barcode}^FS")
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
