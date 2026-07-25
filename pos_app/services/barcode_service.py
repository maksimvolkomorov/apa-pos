"""Barcode generation and product label printing service.

Primary path  : python-barcode + Pillow (PNG file) — if installed.
Fallback path : pure-Python Code128B encoder → PNG via stdlib zlib/struct.
Canvas helper : draw Code128B bars directly on a tk.Canvas (no file needed).
Label printing: ZPL (via services.zebra_service) or PDF, per config.BARCODE_MODE.
"""
import io
import os
import struct
import subprocess
import sys
import zlib

import config

# ── Code128B lookup table ─────────────────────────────────────────────────────
# Each tuple is (b1,s1,b2,s2,b3,s3) — alternating bar/space widths, sum == 11.
_PATTERNS: tuple[tuple[int, ...], ...] = (
    (2,1,2,2,2,2),(2,2,2,1,2,2),(2,2,2,2,2,1),(1,2,1,2,2,3),  # 0–3
    (1,2,1,3,2,2),(1,3,1,2,2,2),(1,2,2,2,1,3),(1,2,2,3,1,2),  # 4–7
    (1,3,2,2,1,2),(2,2,1,2,1,3),(2,2,1,3,1,2),(2,3,1,2,1,2),  # 8–11
    (1,1,2,2,3,2),(1,2,2,1,3,2),(1,2,2,2,3,1),(1,1,3,2,2,2),  # 12–15
    (1,2,3,1,2,2),(1,2,3,2,2,1),(2,2,3,2,1,1),(2,2,1,1,3,2),  # 16–19
    (2,2,1,2,3,1),(2,1,3,2,1,2),(2,2,3,1,1,2),(3,1,2,1,3,1),  # 20–23
    (3,1,1,2,2,2),(3,2,1,1,2,2),(3,2,1,2,2,1),(3,1,2,2,1,2),  # 24–27
    (3,2,2,1,1,2),(3,2,2,2,1,1),(2,1,2,1,2,3),(2,1,2,3,2,1),  # 28–31
    (2,3,2,1,2,1),(1,1,1,3,2,3),(1,3,1,1,2,3),(1,3,1,3,2,1),  # 32–35
    (1,1,2,3,1,3),(1,3,2,1,1,3),(1,3,2,3,1,1),(2,1,1,3,1,3),  # 36–39
    (2,3,1,1,1,3),(2,3,1,3,1,1),(1,1,2,1,3,3),(1,1,2,3,3,1),  # 40–43
    (1,3,2,1,3,1),(1,1,3,1,2,3),(1,1,3,3,2,1),(1,3,3,1,2,1),  # 44–47
    (3,1,3,1,2,1),(2,1,1,3,3,1),(2,3,1,1,3,1),(2,1,3,1,1,3),  # 48–51
    (2,1,3,3,1,1),(2,1,3,1,3,1),(3,1,1,1,2,3),(3,1,1,3,2,1),  # 52–55
    (3,3,1,1,2,1),(3,1,2,1,1,3),(3,1,2,3,1,1),(3,3,2,1,1,1),  # 56–59
    (3,1,4,1,1,1),(2,2,1,4,1,1),(4,3,1,1,1,1),(1,1,1,2,2,4),  # 60–63
    (1,1,1,4,2,2),(1,2,1,1,2,4),(1,2,1,4,2,1),(1,4,1,1,2,2),  # 64–67
    (1,4,1,2,2,1),(1,1,2,2,1,4),(1,1,2,4,1,2),(1,2,2,1,1,4),  # 68–71
    (1,2,2,4,1,1),(1,4,2,1,1,2),(1,4,2,2,1,1),(2,4,1,2,1,1),  # 72–75
    (2,2,1,1,1,4),(4,1,3,1,1,1),(2,4,1,1,1,2),(1,3,4,1,1,1),  # 76–79
    (1,1,1,2,4,2),(1,2,1,1,4,2),(1,2,1,2,4,1),(1,1,4,2,1,2),  # 80–83
    (1,2,4,1,1,2),(1,2,4,2,1,1),(4,1,1,2,1,2),(4,2,1,1,1,2),  # 84–87
    (4,2,1,2,1,1),(2,1,2,1,4,1),(2,1,4,1,2,1),(4,1,2,1,2,1),  # 88–91
    (1,1,1,1,4,3),(1,1,1,3,4,1),(1,3,1,1,4,1),(1,1,4,1,1,3),  # 92–95
    (1,1,4,3,1,1),(4,1,1,1,1,3),(4,1,1,3,1,1),(1,1,3,1,4,1),  # 96–99
    (1,1,4,1,3,1),(3,1,1,1,4,1),(4,1,1,1,3,1),(2,1,1,4,1,2),  # 100–103
    (2,1,1,2,1,4),(2,1,1,2,3,2),                               # 104–105
)
_START_B = 104
_STOP    = (2,3,3,1,1,1,2)   # 7-element stop pattern


def generate_barcode_number(product_id: int) -> str:
    """Return the auto-generated barcode string for a product ID."""
    return f"APA{product_id:06d}"


# ── Encoding ──────────────────────────────────────────────────────────────────

def _encode(text: str) -> list[int]:
    """Encode text as a list of Code128B symbol values (data only, no start/stop)."""
    values = []
    for ch in text:
        v = ord(ch) - 32
        if not (0 <= v <= 95):
            raise ValueError(f"Character {ch!r} (ord={ord(ch)}) outside Code128B range.")
        values.append(v)
    return values


def _checksum(data_values: list[int]) -> int:
    total = _START_B + sum((i + 1) * v for i, v in enumerate(data_values))
    return total % 103


def _bar_units(text: str) -> list[tuple[bool, int]]:
    """
    Return flat list of (is_black, n_units) for the full symbol including
    quiet zones, start, data, checksum and stop.
    """
    data   = _encode(text)
    check  = _checksum(data)
    result: list[tuple[bool, int]] = []

    def add_pattern(pat: tuple[int, ...]) -> None:
        for i, w in enumerate(pat):
            result.append((i % 2 == 0, w))   # even index → bar, odd → space

    # Leading quiet zone (10 units of white)
    result.append((False, 10))
    add_pattern(_PATTERNS[_START_B])
    for v in data:
        add_pattern(_PATTERNS[v])
    add_pattern(_PATTERNS[check])
    add_pattern(_STOP)
    # Trailing quiet zone
    result.append((False, 10))
    return result


# ── Canvas drawing (no files, no deps) ───────────────────────────────────────

def draw_on_canvas(canvas, text: str, *, x: int = 0, y: int = 0,
                   bar_height: int = 60, scale: int = 2) -> int:
    """
    Draw a Code128B barcode onto *canvas* starting at (x, y).
    Returns the total pixel width rendered.
    """
    bars = _bar_units(text)
    cx = x
    for is_black, units in bars:
        w = units * scale
        if is_black:
            canvas.create_rectangle(cx, y, cx + w, y + bar_height,
                                    fill="black", outline="")
        cx += w
    return cx - x


def barcode_pixel_width(text: str, scale: int = 2) -> int:
    return sum(u * scale for _, u in _bar_units(text))


# ── PNG file generation ───────────────────────────────────────────────────────

def generate_barcode_png(barcode: str,
                         output_dir: str | None = None,
                         write_text: bool = True) -> str:
    """
    Generate a Code128B PNG for *barcode*.

    Tries python-barcode + Pillow first; falls back to a pure-stdlib PNG writer
    (bars only — the fallback never bakes in the human-readable text).
    Returns the absolute path to the PNG file.
    """
    out_dir = output_dir or config.BARCODE_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    stem = barcode if write_text else f"{barcode}_notext"
    dest = os.path.join(out_dir, f"{stem}.png")

    # ── primary: python-barcode + Pillow ──────────────────────────────────────
    try:
        import barcode as _bc
        from barcode.writer import ImageWriter
        bc = _bc.get("code128", barcode, writer=ImageWriter())
        bc.save(os.path.join(out_dir, stem), options={"write_text": write_text})
        return dest
    except ImportError:
        pass

    # ── fallback: pure-stdlib PNG ─────────────────────────────────────────────
    _write_png(barcode, dest, scale=3, bar_height=80)
    return dest


# ── Pure-stdlib PNG writer ────────────────────────────────────────────────────

def _write_png(text: str, path: str, scale: int, bar_height: int) -> None:
    """Write a monochrome PNG for *text* using only zlib + struct (stdlib)."""
    bars  = _bar_units(text)
    width = sum(u * scale for _, u in bars)

    # Build a single pixel row (0=black, 255=white, 8-bit greyscale)
    row: list[int] = []
    for is_black, units in bars:
        row.extend([0 if is_black else 255] * (units * scale))

    # PNG scanline: prepend filter byte 0 (None) to each row
    scanline = bytes([0] + row)
    raw = scanline * bar_height
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig   = b"\x89PNG\r\n\x1a\n"
    ihdr  = chunk(b"IHDR", struct.pack(">IIBBBBB", width, bar_height, 8, 0, 0, 0, 0))
    idat  = chunk(b"IDAT", compressed)
    iend  = chunk(b"IEND", b"")

    with open(path, "wb") as fh:
        fh.write(sig + ihdr + idat + iend)


# ── ZPL label building ────────────────────────────────────────────────────────
# Original design was tuned for a 203 DPI printer; these constants preserve
# the same physical (inch) proportions at any config.ZEBRA_DPI, and widen the
# barcode module so the bars scale up to use the label's full width.
_BC_MARGIN_IN     = 0.148   # 30/203
_BC_TITLE_SIZE_IN = 0.128   # matches _BC_PRICE_SIZE_IN — product name uses the same size/style as price
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
_BC_WIDTH_DOTS  = round(config.BARCODE_WIDTH_IN  * config.ZEBRA_DPI)
_BC_HEIGHT_DOTS = round(config.BARCODE_HEIGHT_IN * config.ZEBRA_DPI)

def _fit_name_1line(title: str) -> str:
    """
    Single-line product name at a fixed font size — no shrinking.
    Shared by the ZPL and PDF label builders.

    The title size is sized to fit 6 space-separated 4-letter words
    (29 chars) on the label's printable width; names longer than that
    overflow rather than shrink.
    """
    return title.upper().strip()


def build_product_zpl(title: str, barcode: str, price: float | None = None) -> str:
    """
    Build a ZPL barcode label for the Zebra printer on gapped label stock.

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
    from services.zebra_service import find_ttf_fonts, image_to_zpl_gf

    name = _fit_name_1line(title)
    title_h = _BC_TITLE_H
    price_line = f"{config.CURRENCY_SYMBOL}{price:.2f}" if price is not None else ""

    reg_path, bold_path = find_ttf_fonts()

    def font(size: int, bold: bool = False):
        path = (bold_path or reg_path) if bold else reg_path
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()

    f_title = font(title_h)
    f_price = font(_BC_PRICE_H)
    f_num   = font(round(_BC_PRICE_H * 0.85))

    width = _BC_WIDTH_DOTS
    img   = Image.new("L", (width, 2000), 255)   # generous height; cropped below
    draw  = ImageDraw.Draw(img)

    y = round(15 * _BC_SCALE)
    draw.text((_BC_MARGIN, y), name, font=f_title, fill=0)
    y += _BC_PITCH

    if price_line:
        y += round(4 * _BC_SCALE)
        draw.text((_BC_MARGIN, y), price_line, font=f_price, fill=0)
    y += round(38 * _BC_SCALE)

    # Code128 bars, drawn at an explicit target width — no firmware cap.
    bars       = _bar_units(barcode)
    total_units = sum(u for _, u in bars)
    max_bar_w  = 0.75 * (width - _BC_MARGIN * 2)
    scale      = max_bar_w / total_units

    cx = _BC_MARGIN + (width - _BC_MARGIN * 2 - max_bar_w) / 2
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

    # Crop to the label's fixed physical height (not the content height) —
    # the printer is told the true, constant label pitch below (^LL) so it
    # stays in registration with the die-cut gaps on gapped label stock;
    # content that overflows the physical label is clipped rather than
    # silently growing the label and drifting off the gap on every print.
    cropped = img.crop((0, 0, width, min(y, _BC_HEIGHT_DOTS)))
    gf_cmd, gw, gh = image_to_zpl_gf(cropped)

    header = f"^XA\n^MNY\n^PW{width}\n^LL{_BC_HEIGHT_DOTS}\n^CI28\n"
    return header + f"^FO0,0{gf_cmd}^FS\n^XZ\n"


def _build_product_zpl_fields(title: str, barcode: str, price: float | None = None) -> str:
    """Fallback ZPL builder using native ^BCN (no Pillow required; bar width capped at ^BY's max of 10)."""
    name = _fit_name_1line(title)
    title_h = _BC_TITLE_H
    price_line = f"{config.CURRENCY_SYMBOL}{price:.2f}" if price is not None else ""

    zpl_lines = ["^XA", "^MNY", f"^PW{_BC_WIDTH_DOTS}", "^CI28"]

    y = round(15 * _BC_SCALE)
    zpl_lines.append(f"^FO{_BC_MARGIN},{y}^A0N,{title_h},{title_h}^FD{name}^FS")
    y += _BC_PITCH

    price_y   = y + round(4 * _BC_SCALE)
    barcode_y = price_y + round(34 * _BC_SCALE)

    # Fixed physical label height (^LL), not content-dependent — keeps the
    # printer in registration with the die-cut gaps (see _build_product_zpl_image).
    zpl_lines.append(f"^LL{_BC_HEIGHT_DOTS}")
    zpl_lines.append(f"^FO{_BC_MARGIN},{price_y}^A0N,{_BC_PRICE_H},{_BC_PRICE_H}^FD{price_line}^FS")
    zpl_lines.append(f"^BY{_BC_MODULE},2,{_BC_BAR_HEIGHT}")
    zpl_lines.append(f"^FO{_BC_MARGIN},{barcode_y}^BCN,{_BC_BAR_HEIGHT},Y,N,N^FD{barcode}^FS")
    zpl_lines.append("^XZ")
    return "\n".join(zpl_lines) + "\n"


# ── Label printing dispatch ───────────────────────────────────────────────────

def print_barcode_label(title: str, barcode: str,
                        price: float | None = None) -> None:
    """Print a barcode label via config.BARCODE_MODE ('zebra', 'pdf', 'none')."""
    mode = config.BARCODE_MODE
    if mode == "zebra":
        from services.zebra_service import print_label_usb
        zpl = build_product_zpl(title, barcode, price)
        print_label_usb(zpl)
    elif mode == "pdf":
        _print_barcode_pdf(title, barcode, price)


def _print_barcode_pdf(title: str, barcode: str, price: float | None) -> None:
    os.makedirs(config.BARCODE_OUTPUT_DIR, exist_ok=True)
    pdf_path = os.path.join(config.BARCODE_OUTPUT_DIR, f"label_{barcode}.pdf")

    try:
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas as rl_canvas

        name_font  = "Helvetica"   # matches price's regular style (see _BC_TITLE_SIZE_IN above)
        name       = _fit_name_1line(title)
        name_size  = round(_BC_TITLE_SIZE_IN * 72, 1)
        line_h     = 0.18 * inch
        margin     = _BC_MARGIN_IN * inch
        page_w     = config.BARCODE_WIDTH_IN * inch

        # Height: name line + price + barcode + margins
        page_h = line_h + 0.22 * inch + 0.85 * inch + 0.12 * inch
        c = rl_canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

        y = page_h - 0.16 * inch
        c.setFont(name_font, name_size)
        c.drawString(margin, y, name)
        y -= line_h

        if price is not None:
            y -= 0.02 * inch
            c.setFont("Helvetica", round(_BC_PRICE_SIZE_IN * 72, 1))
            c.drawString(margin, y, f"{config.CURRENCY_SYMBOL}{price:.2f}")
            y -= 0.18 * inch

        y -= 0.04 * inch
        # Bars-only PNG (no baked-in text) — stretching width/height
        # independently only affects bar height, never the encoded
        # bar-width ratios, so this is safe and gives a predictable,
        # full-width label regardless of the source PNG's proportions.
        # The human-readable text is drawn separately below, undistorted.
        png = generate_barcode_png(barcode, write_text=False)
        bar_w  = 0.75 * (page_w - margin * 2)
        bar_h  = _BC_BAR_HEIGHT_IN * inch
        text_h = 0.16 * inch
        bar_y  = 0.06 * inch + text_h
        c.drawImage(png, (page_w - bar_w) / 2, bar_y,
                    width=bar_w, height=bar_h)
        c.setFont("Courier", round(_BC_PRICE_SIZE_IN * 72, 1))
        c.drawCentredString(page_w / 2, 0.06 * inch, barcode)
        c.save()
        actual = pdf_path

    except ImportError:
        actual = generate_barcode_png(barcode)

    if sys.platform == "win32":
        os.startfile(actual)
    elif sys.platform == "darwin":
        subprocess.run(["open", actual], check=False)
    else:
        subprocess.run(["xdg-open", actual], check=False)
