"""Barcode generation service.

Primary path  : python-barcode + Pillow (PNG file) — if installed.
Fallback path : pure-Python Code128B encoder → PNG via stdlib zlib/struct.
Canvas helper : draw Code128B bars directly on a tk.Canvas (no file needed).
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


# ── Label printing dispatch ───────────────────────────────────────────────────

def print_barcode_label(title: str, barcode: str,
                        price: float | None = None) -> None:
    """Print a barcode label via config.BARCODE_MODE ('zebra', 'pdf', 'none')."""
    mode = config.BARCODE_MODE
    if mode == "zebra":
        from services.zebra_service import build_product_zpl, print_label_usb
        zpl = build_product_zpl(title, barcode, price)
        print_label_usb(zpl)
    elif mode == "pdf":
        _print_barcode_pdf(title, barcode, price)


def _wrap_pdf_name(title: str, font: str, size: float, max_w: float) -> list[str]:
    """Word-wrap title into at most 2 lines fitting max_w pixels."""
    from reportlab.pdfbase.pdfmetrics import stringWidth as sw
    upper = title.upper().strip()
    if sw(upper, font, size) <= max_w:
        return [upper]
    words = upper.split()
    line1: list[str] = []
    for word in words:
        if sw(" ".join(line1 + [word]), font, size) <= max_w:
            line1.append(word)
        else:
            break
    l1 = " ".join(line1)
    l2 = " ".join(words[len(line1):])
    if not l1:
        for i in range(len(upper) - 1, 0, -1):
            if sw(upper[:i] + "...", font, size) <= max_w:
                return [upper[:i] + "..."]
        return ["..."]
    if not l2:
        return [l1]
    if sw(l2, font, size) <= max_w:
        return [l1, l2]
    for i in range(len(l2) - 1, 0, -1):
        if sw(l2[:i] + "...", font, size) <= max_w:
            return [l1, l2[:i] + "..."]
    return [l1, "..."]


def _print_barcode_pdf(title: str, barcode: str, price: float | None) -> None:
    os.makedirs(config.BARCODE_OUTPUT_DIR, exist_ok=True)
    pdf_path = os.path.join(config.BARCODE_OUTPUT_DIR, f"label_{barcode}.pdf")

    try:
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas as rl_canvas
        from services.zebra_service import (_BC_MARGIN_IN, _BC_TITLE_SIZE_IN,
                                            _BC_PRICE_SIZE_IN, _BC_BAR_HEIGHT_IN)

        name_font  = "Helvetica-Bold"
        name_size  = round(_BC_TITLE_SIZE_IN * 72, 1)
        line_h     = 0.18 * inch
        margin     = _BC_MARGIN_IN * inch
        page_w     = config.RECEIPT_WIDTH_IN * inch
        max_name_w = page_w - margin * 2

        name_lines = _wrap_pdf_name(title, name_font, name_size, max_name_w)
        n_name     = len(name_lines)

        # Height: name lines + price + barcode + margins
        page_h = (n_name * line_h) + 0.22 * inch + 0.85 * inch + 0.12 * inch
        c = rl_canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

        y = page_h - 0.16 * inch
        c.setFont(name_font, name_size)
        for nl in name_lines:
            c.drawString(margin, y, nl)
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
