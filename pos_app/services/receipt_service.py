"""Receipt service — build and dispatch order receipts after checkout.

Dispatch mode is driven by config.RECEIPT_MODE:
  "zebra" — ZPL receipt sent to Zebra GX420D via USB
  "pdf"   — PDF saved to config.RECEIPT_OUTPUT_DIR then opened (plain-text
             .txt fallback when reportlab is not installed)
  "none"  — silent; no receipt produced
"""
import os
import subprocess
import sys
from datetime import datetime

import config

# ── Unicode font registration (Cyrillic support) ──────────────────────────────
_FONT_REGULAR = "Helvetica"
_FONT_BOLD    = "Helvetica-Bold"

def _register_fonts() -> None:
    """Register a Unicode-capable TTF font for PDF output. No-op if already done."""
    global _FONT_REGULAR, _FONT_BOLD
    if _FONT_REGULAR != "Helvetica":
        return
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.fonts import addMapping

        candidates = [
            ("C:/Windows/Fonts/arial.ttf",   "C:/Windows/Fonts/arialbd.ttf"),
            ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
            ("/Library/Fonts/Arial.ttf",     "/Library/Fonts/Arial Bold.ttf"),
        ]
        for reg, bold in candidates:
            if os.path.exists(reg) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("AppFont",      reg))
                pdfmetrics.registerFont(TTFont("AppFont-Bold", bold))
                pdfmetrics.registerFontFamily(
                    "AppFont",
                    normal="AppFont",
                    bold="AppFont-Bold",
                    italic="AppFont",
                    boldItalic="AppFont-Bold",
                )
                _FONT_REGULAR = "AppFont"
                _FONT_BOLD    = "AppFont-Bold"
                break
    except Exception:
        pass


def _apply_font_to_styles(styles) -> None:
    """Override default Helvetica in reportlab stylesheet with the registered font."""
    for s in styles.byName.values():
        if hasattr(s, "fontName"):
            if "Bold" in (s.fontName or ""):
                s.fontName = _FONT_BOLD
            else:
                s.fontName = _FONT_REGULAR


# Receipt width constants for ZPL (4" @ 203 DPI)
_ZPL_WIDTH_DOTS = 812
_FONT_H         = 26   # font height in dots (body text)
_LINE_H         = 34   # line pitch in dots
_MARGIN_X       = 20
_SEP_Y_PAD      = 6    # vertical padding around a separator line

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dt(iso: str) -> str:
    """ISO datetime → US display format ('06/21/2026 02:30 PM')."""
    try:
        return datetime.strptime(iso[:16], "%Y-%m-%d %H:%M").strftime("%m/%d/%Y %I:%M %p")
    except (ValueError, TypeError):
        return iso

# Text receipt width in characters (for PDF/txt)
_TXT_WIDTH = 42

_VOWELS = set("AEIOU")


_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but",
    "in", "on", "at", "to", "of", "for",
    "by", "as", "is", "it", "its", "from",
    "with", "this", "that",
}


def _clean_name(name: str) -> str:
    """Keep only alphanumeric chars, strip stop words (articles/prepositions)."""
    words = ["".join(c for c in w if c.isalnum()) for w in name.split()]
    filtered = [w for w in words if w and w.lower() not in _STOP_WORDS]
    return " ".join(filtered).strip()


def _abbr_words(name: str) -> str:
    """Uppercase + drop vowels from every word except the first letter."""
    words = name.upper().split()
    return " ".join(w[0] + "".join(c for c in w[1:] if c not in _VOWELS) for w in words)


def _abbreviate(name: str, max_chars: int) -> str:
    """Fit name into max_chars: uppercase → abbreviate → truncate."""
    name  = _clean_name(name)
    upper = name.upper()
    if len(upper) <= max_chars:
        return upper
    abbreviated = _abbr_words(name)
    if len(abbreviated) <= max_chars:
        return abbreviated
    return abbreviated[: max_chars - 1] + "…"


def _abbreviate_px(name: str, font: str, size: float, max_w: float) -> str:
    """Pixel-accurate version of _abbreviate for proportional fonts (reportlab)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth as sw
    name  = _clean_name(name)
    upper = name.upper()
    if sw(upper, font, size) <= max_w:
        return upper
    abbreviated = _abbr_words(name)
    if sw(abbreviated, font, size) <= max_w:
        return abbreviated
    # Truncate character by character
    for i in range(len(abbreviated) - 1, 0, -1):
        candidate = abbreviated[:i] + "…"
        if sw(candidate, font, size) <= max_w:
            return candidate
    return "…"


# ── Public API ────────────────────────────────────────────────────────────────

def print_receipt(order: dict, items: list[dict]) -> None:
    """
    Dispatch a receipt according to config.RECEIPT_MODE.
    Raises OSError / IOError on failure so the caller can show a warning.
    """
    mode    = config.RECEIPT_MODE
    is_gift = order.get("payment_method") == "gift"

    if mode == "zebra":
        from services.zebra_service import print_label_usb
        zpl = build_gift_receipt_zpl(order, items) if is_gift else build_receipt_zpl(order, items)
        print_label_usb(zpl)

    elif mode == "pdf":
        os.makedirs(config.RECEIPT_OUTPUT_DIR, exist_ok=True)
        requested = os.path.join(
            config.RECEIPT_OUTPUT_DIR,
            f"receipt_{order['id']}.pdf",
        )
        actual_path = (build_gift_receipt_pdf(order, items, requested)
                       if is_gift else build_receipt_pdf(order, items, requested))
        _open_file(actual_path)

    # "none" → do nothing


# ── ZPL receipt ───────────────────────────────────────────────────────────────

def build_receipt_zpl(order: dict, items: list[dict]) -> str:
    """Build a ZPL receipt for the Zebra GX420D on 4" continuous paper."""
    sym      = config.CURRENCY_SYMBOL
    tax_rate = config.TAX_RATE
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    tax      = round(subtotal * tax_rate, 2)
    total    = subtotal + tax

    lines: list[str] = []

    def y_next(y: int, extra: int = 0) -> int:
        return y + _LINE_H + extra

    def text(y: int, content: str, font_h: int = _FONT_H) -> tuple[str, int]:
        cmd = (f"^FO{_MARGIN_X},{y}"
               f"^A0N,{font_h},{font_h}"
               f"^FD{content}^FS")
        return cmd, y_next(y)

    def separator(y: int, thick: int = 1) -> tuple[str, int]:
        cmd = f"^FO{_MARGIN_X},{y + _SEP_Y_PAD}^GB{_ZPL_WIDTH_DOTS - _MARGIN_X * 2},{thick},{thick}^FS"
        return cmd, y + thick + _SEP_Y_PAD * 2

    y = 20

    # Store name
    cmd, y = text(y, config.STORE_NAME, font_h=36)
    lines.append(cmd)

    # Address lines
    for addr_line in config.STORE_ADDRESS:
        cmd, y = text(y, addr_line, font_h=22)
        lines.append(cmd)

    # Date + order ID
    dt = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))
    cmd, y = text(y, dt)
    lines.append(cmd)
    cmd, y = text(y, f"Order #{order['id']}")
    lines.append(cmd)

    # Separator
    cmd, y = separator(y, thick=2)
    lines.append(cmd)

    # Line items — name line then indented qty + price line
    _ZPL_CHARS = 42
    for item in items:
        name  = _abbreviate(item["product_name"], _ZPL_CHARS)
        qty   = item["quantity"]
        price = item["quantity"] * item["unit_price"]
        cmd, y = text(y, name)
        lines.append(cmd)
        cmd, y = text(y, f"  x{qty:<3}  {sym}{price:.2f}")
        lines.append(cmd)

    # Thin separator
    cmd, y = separator(y)
    lines.append(cmd)

    # Totals
    cmd, y = text(y, f"{'Subtotal':<28} {sym}{subtotal:>7.2f}")
    lines.append(cmd)
    cmd, y = text(y, f"{'Sales Tax':<28} {sym}{tax:>7.2f}")
    lines.append(cmd)

    # Bold separator + TOTAL
    cmd, y = separator(y, thick=2)
    lines.append(cmd)
    cmd, y = text(y, f"{'TOTAL':<28} {sym}{total:>7.2f}", font_h=30)
    lines.append(cmd)

    # Footer
    cmd, y = separator(y)
    lines.append(cmd)
    cmd, y = text(y, "Thank you!", font_h=_FONT_H)
    lines.append(cmd)

    label_height = y + 20   # bottom margin

    header = (
        "^XA\n"
        "^MNC\n"                    # continuous media (no gaps) for thermal tape
        f"^PW{_ZPL_WIDTH_DOTS}\n"
        f"^LL{label_height}\n"
        "^CI28\n"           # UTF-8
    )
    return header + "\n".join(lines) + "\n^XZ\n"


# ── PDF / txt receipt ─────────────────────────────────────────────────────────

def build_receipt_pdf(order: dict, items: list[dict], path: str) -> str:
    """
    Write a receipt and return the actual file path created.
    Uses reportlab for a proper PDF; falls back to a .txt file.
    """
    try:
        _build_pdf_reportlab(order, items, path)
        return path
    except ImportError:
        txt_path = os.path.splitext(path)[0] + ".txt"
        _build_txt(order, items, txt_path)
        return txt_path


def _build_txt(order: dict, items: list[dict], path: str) -> None:
    sym      = config.CURRENCY_SYMBOL
    tax_rate = config.TAX_RATE
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    tax      = round(subtotal * tax_rate, 2)
    total    = subtotal + tax
    w        = _TXT_WIDTH
    dt       = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))

    sep_thick = "=" * w
    sep_thin  = "-" * w

    receipt_lines = [
        sep_thick,
        config.STORE_NAME.center(w),
    ]
    for addr_line in config.STORE_ADDRESS:
        receipt_lines.append(addr_line.center(w))
    receipt_lines += [
        dt.center(w),
        f"Order #{order['id']}".center(w),
        sep_thick,
    ]

    for item in items:
        name  = _abbreviate(item["product_name"], w)
        qty   = item["quantity"]
        price = item["quantity"] * item["unit_price"]
        right = f"{sym}{price:.2f}"
        receipt_lines.append(name)
        gap = w - 2 - len(f"x{qty}") - len(right)
        receipt_lines.append(f"  x{qty}" + " " * max(gap, 1) + right)

    receipt_lines += [
        sep_thin,
        _total_line("Subtotal", f"{sym}{subtotal:.2f}", w),
        _total_line("Sales Tax", f"{sym}{tax:.2f}", w),
        sep_thick,
        _total_line("TOTAL", f"{sym}{total:.2f}", w),
        sep_thick,
        "Thank you!".center(w),
        "",
    ]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(receipt_lines))


def _total_line(label: str, value: str, width: int) -> str:
    gap = width - len(label) - len(value) - 2
    return f"  {label}" + " " * max(gap, 1) + value


def _build_pdf_reportlab(order: dict, items: list[dict], path: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    _register_fonts()

    sym      = config.CURRENCY_SYMBOL
    tax_rate = config.TAX_RATE
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    tax      = round(subtotal * tax_rate, 2)
    total    = subtotal + tax
    dt       = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))

    # Receipt paper: 80 mm wide, auto height
    page_w   = 80 * mm
    line_h   = 14
    margin   = 8 * mm
    n_lines  = 8 + len(items) * 2
    page_h   = (n_lines * line_h + 60) * 1.0

    c   = rl_canvas.Canvas(path, pagesize=(page_w, page_h))
    y   = page_h - 20

    def draw(txt: str, size: int = 9, bold: bool = False, centre: bool = False):
        nonlocal y
        c.setFont(_FONT_BOLD if bold else _FONT_REGULAR, size)
        x = margin if not centre else page_w / 2
        anchor = "left" if not centre else "middle"
        if centre:
            c.drawCentredString(x, y, txt)
        else:
            c.drawString(x, y, txt)
        y -= line_h

    def hline(thick: float = 0.5):
        nonlocal y
        c.setLineWidth(thick)
        c.line(margin, y + line_h * 0.4, page_w - margin, y + line_h * 0.4)
        y -= 4

    draw(config.STORE_NAME,        size=13, bold=True, centre=True)
    for addr_line in config.STORE_ADDRESS:
        draw(addr_line,            size=8,             centre=True)
    draw(dt,                       size=9,             centre=True)
    draw(f"Order #{order['id']}", size=9,              centre=True)
    hline(thick=1.5)

    for item in items:
        max_name_w = page_w - margin * 2
        name  = _abbreviate_px(item["product_name"], _FONT_REGULAR, 9, max_name_w)
        qty   = item["quantity"]
        price = item["quantity"] * item["unit_price"]
        c.setFont(_FONT_REGULAR, 9)
        c.drawString(margin, y, name)
        y -= line_h
        c.drawString(margin, y, f"  x{qty}")
        c.drawRightString(page_w - margin, y, f"{sym}{price:.2f}")
        y -= line_h

    hline()
    c.setFont(_FONT_REGULAR, 9)
    c.drawString(margin, y, "Subtotal")
    c.drawRightString(page_w - margin, y, f"{sym}{subtotal:.2f}")
    y -= line_h
    c.drawString(margin, y, "Sales Tax")
    c.drawRightString(page_w - margin, y, f"{sym}{tax:.2f}")
    y -= line_h
    hline(thick=1.5)
    c.setFont(_FONT_BOLD, 11)
    c.drawString(margin, y, "TOTAL")
    c.drawRightString(page_w - margin, y, f"{sym}{total:.2f}")
    y -= line_h
    hline()
    draw("Thank you!", size=9, centre=True)

    c.save()


# ── Gift receipts ─────────────────────────────────────────────────────────────

def build_gift_receipt_zpl(order: dict, items: list[dict]) -> str:
    """ZPL gift receipt — items listed, no prices, no totals."""
    lines: list[str] = []

    def y_next(y): return y + _LINE_H

    def text(y, content, font_h=_FONT_H):
        cmd = f"^FO{_MARGIN_X},{y}^A0N,{font_h},{font_h}^FD{content}^FS"
        return cmd, y_next(y)

    def separator(y, thick=1):
        cmd = f"^FO{_MARGIN_X},{y + _SEP_Y_PAD}^GB{_ZPL_WIDTH_DOTS - _MARGIN_X * 2},{thick},{thick}^FS"
        return cmd, y + thick + _SEP_Y_PAD * 2

    y = 20
    cmd, y = text(y, config.STORE_NAME, font_h=36); lines.append(cmd)
    for addr_line in config.STORE_ADDRESS:
        cmd, y = text(y, addr_line, font_h=22); lines.append(cmd)

    cmd, y = text(y, "** GIFT RECEIPT **", font_h=28); lines.append(cmd)
    dt = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))
    cmd, y = text(y, dt); lines.append(cmd)
    cmd, y = text(y, f"Order #{order['id']}"); lines.append(cmd)
    cmd, y = separator(y, thick=2); lines.append(cmd)

    for item in items:
        name = _abbreviate(item["product_name"], 42)
        cmd, y = text(y, name); lines.append(cmd)
        cmd, y = text(y, f"  x{item['quantity']}"); lines.append(cmd)

    cmd, y = separator(y); lines.append(cmd)
    cmd, y = text(y, "Thank you!", font_h=_FONT_H); lines.append(cmd)

    label_height = y + 20
    header = (f"^XA\n^MNC\n^PW{_ZPL_WIDTH_DOTS}\n^LL{label_height}\n^CI28\n")
    return header + "\n".join(lines) + "\n^XZ\n"


def build_gift_receipt_pdf(order: dict, items: list[dict], path: str) -> str:
    try:
        _build_gift_pdf_reportlab(order, items, path)
        return path
    except ImportError:
        txt_path = os.path.splitext(path)[0] + ".txt"
        _build_gift_txt(order, items, txt_path)
        return txt_path


def _build_gift_txt(order: dict, items: list[dict], path: str) -> None:
    w  = _TXT_WIDTH
    dt = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))
    lines = [
        "=" * w,
        config.STORE_NAME.center(w),
        "** GIFT RECEIPT **".center(w),
        dt.center(w),
        f"Order #{order['id']}".center(w),
        "=" * w,
    ]
    for item in items:
        lines.append(_abbreviate(item["product_name"], w))
        lines.append(f"  x{item['quantity']}")
    lines += ["=" * w, "Thank you!".center(w), ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _build_gift_pdf_reportlab(order: dict, items: list[dict], path: str) -> None:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    _register_fonts()

    page_w  = 80 * mm
    line_h  = 14
    margin  = 8 * mm
    page_h  = (8 + len(items) * 2) * line_h + 60
    c       = rl_canvas.Canvas(path, pagesize=(page_w, page_h))
    y       = page_h - 20
    dt      = _fmt_dt(order.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M")))

    def draw(txt, size=9, bold=False, centre=False):
        nonlocal y
        c.setFont(_FONT_BOLD if bold else _FONT_REGULAR, size)
        if centre:
            c.drawCentredString(page_w / 2, y, txt)
        else:
            c.drawString(margin, y, txt)
        y -= line_h

    def hline(thick=0.5):
        nonlocal y
        c.setLineWidth(thick)
        c.line(margin, y + line_h * 0.4, page_w - margin, y + line_h * 0.4)
        y -= 4

    draw(config.STORE_NAME, size=13, bold=True, centre=True)
    for addr_line in config.STORE_ADDRESS:
        draw(addr_line, size=8, centre=True)
    draw("** GIFT RECEIPT **", size=11, bold=True, centre=True)
    draw(dt, centre=True)
    draw(f"Order #{order['id']}", centre=True)
    hline(thick=1.5)
    for item in items:
        name = _abbreviate_px(item["product_name"], _FONT_REGULAR, 9, page_w - margin * 2)
        c.setFont(_FONT_REGULAR, 9)
        c.drawString(margin, y, name)
        y -= line_h
        c.drawString(margin, y, f"  x{item['quantity']}")
        y -= line_h
    hline()
    draw("Thank you!", size=9, centre=True)
    c.save()


# ── Detailed sales report ────────────────────────────────────────────────────

def _build_detailed_pdf_reportlab(orders, date_from, date_to, path, now):
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet
    _register_fonts()
    styles = getSampleStyleSheet()
    _apply_font_to_styles(styles)

    sym    = config.CURRENCY_SYMBOL
    period = f"{date_from or 'All'} – {date_to or 'All'}"

    doc = SimpleDocTemplate(path, pagesize=LETTER,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch,  bottomMargin=0.5*inch)

    title_style  = styles["Title"]
    normal       = styles["Normal"]
    normal.fontSize = 9

    bold_style = styles["Normal"].__class__(
        "Bold9", parent=styles["Normal"],
        fontName=_FONT_BOLD, fontSize=9,
    )

    story = []
    story.append(Paragraph("DETAILED SALES REPORT", title_style))
    story.append(Paragraph(config.STORE_NAME, normal))
    story.append(Paragraph(f"Period: {period}", normal))
    story.append(Paragraph(_fmt_dt(now.strftime("%Y-%m-%d %H:%M")), normal))
    story.append(Spacer(1, 0.15*inch))

    from models import order as order_model

    grand_sub = grand_disc = grand_tax = grand_total = 0.0

    for o in orders:
        items   = order_model.get_items(o["id"])
        sub     = sum(i["quantity"] * i["unit_price"] for i in items)
        disc    = o.get("discount_pct") or 0
        disc_amt = round(sub * disc / 100, 2)
        tax     = round((sub - disc_amt) * config.TAX_RATE, 2)
        total   = o["total"]
        method  = (o.get("payment_method") or "cash").upper()
        by      = o.get("processed_by") or "—"

        grand_sub   += sub
        grand_disc  += disc_amt
        grand_tax   += tax
        grand_total += total

        # Order header row
        hdr_data = [[
            Paragraph(f"<b>Order #{o['id']}</b>", normal),
            Paragraph(f"<b>{_fmt_dt(o['created_at'])}</b>", normal),
            Paragraph(f"<b>{method}</b>", normal),
            Paragraph(f"<b>By: {by}</b>", normal),
            Paragraph(f"<b>Total: {sym}{total:.2f}</b>", normal),
        ]]
        hdr_tbl = Table(hdr_data, colWidths=[1.1*inch, 1.8*inch, 0.7*inch, 1.5*inch, 1.3*inch])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#2980B9")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE",    (0, 0), (-1, 0), 9),
            ("TOPPADDING",  (0, 0), (-1, 0), 4),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("VALIGN",      (0, 0), (-1, 0), "MIDDLE"),
        ]))
        story.append(hdr_tbl)

        # Items sub-table
        item_rows = [["Product", "Qty", "Unit Price", "Line Total"]]
        for item in items:
            line = item["quantity"] * item["unit_price"]
            item_rows.append([
                Paragraph(item["product_name"], normal),
                str(item["quantity"]),
                f"{sym}{item['unit_price']:.2f}",
                f"{sym}{line:.2f}",
            ])

        # Subtotals row
        disc_str = f"  disc {disc:.4g}%  −{sym}{disc_amt:.2f}" if disc else ""
        item_rows.append([
            Paragraph(f"<b>Subtotal{disc_str}</b>", normal),
            "", f"Tax {sym}{tax:.2f}",
            Paragraph(f"<b>{sym}{total:.2f}</b>", normal),
        ])

        item_tbl = Table(item_rows,
                         colWidths=[3.4*inch, 0.5*inch, 1.2*inch, 1.3*inch],
                         repeatRows=0)
        item_tbl.setStyle(TableStyle([
            ("FONTNAME",       (0, 0),  (-1, 0),  _FONT_BOLD),
            ("FONTNAME",       (0, 1),  (-1, -1), _FONT_REGULAR),
            ("FONTSIZE",       (0, 0),  (-1, -1), 8),
            ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#ECF0F1")),
            ("ROWBACKGROUNDS", (0, 1),  (-1, -2),
             [colors.white, colors.HexColor("#EAF4FB")]),
            ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#ECF0F1")),
            ("FONTNAME",       (0, -1), (-1, -1), _FONT_BOLD),
            ("ALIGN",          (1, 0),  (-1, -1), "RIGHT"),
            ("GRID",           (0, 0),  (-1, -1), 0.25, colors.HexColor("#BDC3C7")),
            ("LEFTPADDING",    (0, 0),  (0, -1),  6),
            ("TOPPADDING",     (0, 0),  (-1, -1), 3),
            ("BOTTOMPADDING",  (0, 0),  (-1, -1), 3),
            ("VALIGN",         (0, 0),  (-1, -1), "MIDDLE"),
        ]))
        story.append(item_tbl)
        story.append(Spacer(1, 0.12*inch))

    # Grand totals
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2980B9")))
    story.append(Spacer(1, 0.06*inch))
    story.append(Paragraph(
        f"Orders: <b>{len(orders)}</b> &nbsp;&nbsp; "
        f"Subtotal: <b>{sym}{grand_sub:.2f}</b> &nbsp;&nbsp; "
        f"Discounts: <b>−{sym}{grand_disc:.2f}</b> &nbsp;&nbsp; "
        f"Tax: <b>{sym}{grand_tax:.2f}</b> &nbsp;&nbsp; "
        f"Total Revenue: <b>{sym}{grand_total:.2f}</b>",
        normal,
    ))
    doc.build(story)


def build_detailed_report_pdf(orders: list[dict],
                               date_from: str | None,
                               date_to:   str | None) -> str:
    """Generate a detailed per-order report PDF, open it, return the path."""
    os.makedirs(config.RECEIPT_OUTPUT_DIR, exist_ok=True)
    now  = datetime.now()
    stem = f"detailed_report_{now.strftime('%Y%m%d_%H%M%S')}"
    pdf_path = os.path.join(config.RECEIPT_OUTPUT_DIR, stem + ".pdf")
    try:
        _build_detailed_pdf_reportlab(orders, date_from, date_to, pdf_path, now)
        _open_file(pdf_path)
        return pdf_path
    except ImportError:
        raise RuntimeError("reportlab is required for PDF reports.")


# ── Sales report ─────────────────────────────────────────────────────────────

def build_sales_report_pdf(orders: list[dict],
                            date_from: str | None,
                            date_to:   str | None) -> str:
    """
    Generate a sales report PDF for the given orders, open it, and return
    the file path (.pdf or .txt fallback).
    """
    os.makedirs(config.RECEIPT_OUTPUT_DIR, exist_ok=True)
    now  = datetime.now()
    stem = f"sales_report_{now.strftime('%Y%m%d_%H%M%S')}"
    pdf_path = os.path.join(config.RECEIPT_OUTPUT_DIR, stem + ".pdf")

    try:
        _build_sales_pdf_reportlab(orders, date_from, date_to, pdf_path, now)
        actual = pdf_path
    except ImportError:
        txt_path = os.path.join(config.RECEIPT_OUTPUT_DIR, stem + ".txt")
        _build_sales_txt(orders, date_from, date_to, txt_path, now)
        actual = txt_path

    _open_file(actual)
    return actual


def _sales_order_row(order: dict) -> tuple:
    """Return (items, subtotal, discount_amt, tax, total) for one order."""
    from models.order import get_items
    items    = get_items(order["id"])
    is_gift  = order.get("payment_method") == "gift"
    if is_gift:
        item_count = sum(i["quantity"] for i in items)
        return item_count, 0.0, 0.0, 0.0, 0.0
    subtotal    = sum(i["quantity"] * i["unit_price"] for i in items)
    disc_pct    = order.get("discount_pct") or 0.0
    disc_amt    = round(subtotal * disc_pct / 100, 2)
    taxable     = subtotal - disc_amt
    tax         = round(taxable * config.TAX_RATE, 2)
    total       = taxable + tax
    item_count  = sum(i["quantity"] for i in items)
    return item_count, subtotal, disc_amt, tax, total


def _build_sales_txt(orders, date_from, date_to, path, now):
    sym = config.CURRENCY_SYMBOL
    w   = 100
    period = f"{date_from or 'All'} – {date_to or 'All'}"

    lines = [
        "=" * w,
        "SALES REPORT".center(w),
        config.STORE_NAME.center(w),
        f"Period: {period}".center(w),
        _fmt_dt(now.strftime("%Y-%m-%d %H:%M")).center(w),
        "=" * w,
        f"{'ID':>5}  {'Date/Time':<18}  {'By':<14}  {'Pay':<5}  "
        f"{'Items':>5}  {'Subtotal':>9}  {'Disc':>8}  {'Tax':>8}  {'Total':>9}",
        "-" * w,
    ]

    tot_items = tot_sub = tot_disc = tot_tax = tot_total = 0.0
    for o in orders:
        cnt, sub, disc, tax, total = _sales_order_row(o)
        method = (o.get("payment_method") or "cash").upper()[:5]
        by     = (o.get("processed_by") or "")[:14]
        dt     = (o.get("created_at") or "")[:16]
        lines.append(
            f"{o['id']:>5}  {dt:<18}  {by:<14}  {method:<5}  "
            f"{cnt:>5}  {sym}{sub:>8.2f}  {sym}{disc:>7.2f}  "
            f"{sym}{tax:>7.2f}  {sym}{total:>8.2f}"
        )
        tot_items += cnt; tot_sub += sub; tot_disc += disc
        tot_tax   += tax; tot_total += total

    lines += [
        "=" * w,
        f"{'Orders: ' + str(len(orders)):>5}  {'':18}  {'':14}  {'':5}  "
        f"{tot_items:>5}  {sym}{tot_sub:>8.2f}  {sym}{tot_disc:>7.2f}  "
        f"{sym}{tot_tax:>7.2f}  {sym}{tot_total:>8.2f}",
        "=" * w, "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _build_sales_pdf_reportlab(orders, date_from, date_to, path, now):
    from reportlab.lib.pagesizes import LETTER, landscape
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    _register_fonts()
    from reportlab.lib.styles import getSampleStyleSheet

    styles = getSampleStyleSheet()
    _apply_font_to_styles(styles)

    sym    = config.CURRENCY_SYMBOL
    period = f"{date_from or 'All'} – {date_to or 'All'}"

    doc    = SimpleDocTemplate(path, pagesize=landscape(LETTER),
                               leftMargin=0.5*inch, rightMargin=0.5*inch,
                               topMargin=0.5*inch,  bottomMargin=0.5*inch)
    cs       = styles["Normal"]
    cs.fontSize = 9
    story  = []

    story.append(Paragraph("SALES REPORT", styles["Title"]))
    story.append(Paragraph(config.STORE_NAME, styles["Normal"]))
    story.append(Paragraph(f"Period: {period}", styles["Normal"]))
    story.append(Paragraph(_fmt_dt(now.strftime("%Y-%m-%d %H:%M")), styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    header = ["ID", "Date / Time", "Processed By", "Payment", "Items",
              "Subtotal", "Discount", "Tax", "Total"]
    rows   = [header]

    tot_items = tot_sub = tot_disc = tot_tax = tot_total = 0.0
    for o in orders:
        cnt, sub, disc, tax, total = _sales_order_row(o)
        method  = (o.get("payment_method") or "cash").upper()
        by      = o.get("processed_by") or "—"
        dt      = _fmt_dt(o.get("created_at") or "")
        rows.append([
            str(o["id"]), dt, Paragraph(by, cs), method,
            str(int(cnt)),
            f"{sym}{sub:.2f}", f"{sym}{disc:.2f}",
            f"{sym}{tax:.2f}", f"{sym}{total:.2f}",
        ])
        tot_items += cnt; tot_sub += sub; tot_disc += disc
        tot_tax   += tax; tot_total += total

    rows.append([
        f"{len(orders)} orders", "", "", "", str(int(tot_items)),
        f"{sym}{tot_sub:.2f}", f"{sym}{tot_disc:.2f}",
        f"{sym}{tot_tax:.2f}", f"{sym}{tot_total:.2f}",
    ])

    col_widths = [0.45*inch, 1.5*inch, 1.4*inch, 0.8*inch, 0.5*inch,
                  0.85*inch, 0.85*inch, 0.75*inch, 0.85*inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),   colors.HexColor("#2980B9")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),   colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),   _FONT_BOLD),
        ("FONTNAME",       (0, 1),  (-1, -1),  _FONT_REGULAR),
        ("FONTSIZE",       (0, 0),  (-1, -1),  9),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2),
         [colors.white, colors.HexColor("#EAF4FB")]),
        ("BACKGROUND",     (0, -1), (-1, -1),  colors.HexColor("#ECF0F1")),
        ("FONTNAME",       (0, -1), (-1, -1),  _FONT_BOLD),
        ("ALIGN",          (4, 1),  (-1, -1),  "RIGHT"),
        ("ALIGN",          (0, 0),  (0, -1),   "CENTER"),
        ("GRID",           (0, 0),  (-1, -1),  0.25, colors.HexColor("#BDC3C7")),
        ("VALIGN",         (0, 0),  (-1, -1),  "MIDDLE"),
        ("ROWHEIGHT",      (0, 0),  (-1, -1),  18),
    ]))
    story.append(tbl)

    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph(
        f"Orders: <b>{len(orders)}</b> &nbsp;&nbsp; "
        f"Items sold: <b>{int(tot_items)}</b> &nbsp;&nbsp; "
        f"Revenue: <b>{sym}{tot_total:.2f}</b> &nbsp;&nbsp; "
        f"Tax collected: <b>{sym}{tot_tax:.2f}</b>",
        styles["Normal"],
    ))
    doc.build(story)


# ── OS helpers ────────────────────────────────────────────────────────────────

def _open_file(path: str) -> None:
    """Open *path* with the OS default application."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


# ── Stock report ──────────────────────────────────────────────────────────────

def build_stock_report_pdf(products: list[dict]) -> str:
    """
    Generate a stock report, save to RECEIPT_OUTPUT_DIR, open it, and
    return the actual file path created (.pdf or .txt fallback).
    """
    os.makedirs(config.RECEIPT_OUTPUT_DIR, exist_ok=True)
    now  = datetime.now()
    stem = f"stock_report_{now.strftime('%Y%m%d_%H%M%S')}"

    pdf_path = os.path.join(config.RECEIPT_OUTPUT_DIR, stem + ".pdf")
    try:
        _build_stock_pdf_reportlab(products, pdf_path, now)
        actual = pdf_path
    except ImportError:
        txt_path = os.path.join(config.RECEIPT_OUTPUT_DIR, stem + ".txt")
        _build_stock_txt(products, txt_path, now)
        actual = txt_path

    _open_file(actual)
    return actual


def _build_stock_txt(products: list[dict], path: str, now: datetime) -> None:
    sym = config.CURRENCY_SYMBOL
    w   = 72

    total_units = sum(p["stock"] for p in products)
    total_value = sum(p["stock"] * p["price"] for p in products)

    lines = [
        "=" * w,
        "STOCK REPORT".center(w),
        config.STORE_NAME.center(w),
        _fmt_dt(now.strftime("%Y-%m-%d %H:%M")).center(w),
        "=" * w,
        f"{'ID':<6} {'Name':<28} {'Barcode':<12} {'Stock':>6} {'Price':>8} {'Value':>10}",
        "-" * w,
    ]

    for p in products:
        value      = p["stock"] * p["price"]
        stock_cell = str(p["stock"])
        lines.append(
            f"{p['id']:<6} {p['title'][:28]:<28} {p['barcode']:<12}"
            f" {stock_cell:>6} {sym}{p['price']:>7.2f} {sym}{value:>9.2f}"
        )

    lines += [
        "=" * w,
        f"  Products: {len(products)}   "
        f"Total units: {total_units}   "
        f"Stock value: {sym}{total_value:.2f}",
        "=" * w,
        "",
    ]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _build_stock_pdf_reportlab(products: list[dict], path: str,
                                now: datetime) -> None:
    from reportlab.lib.pagesizes import LETTER, landscape
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet
    _register_fonts()
    styles = getSampleStyleSheet()
    _apply_font_to_styles(styles)

    sym         = config.CURRENCY_SYMBOL
    total_units = sum(p["stock"] for p in products)
    total_value = sum(p["stock"] * p["price"] for p in products)

    doc    = SimpleDocTemplate(path, pagesize=landscape(LETTER),
                               leftMargin=0.5*inch, rightMargin=0.5*inch,
                               topMargin=0.5*inch,  bottomMargin=0.5*inch)
    story  = []

    # Header
    story.append(Paragraph("STOCK REPORT", styles["Title"]))
    story.append(Paragraph(config.STORE_NAME, styles["Normal"]))
    story.append(Paragraph(_fmt_dt(now.strftime("%Y-%m-%d %H:%M")),
                            styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    cell_style = styles["Normal"]
    cell_style.fontSize = 9

    # Table
    header = ["ID", "Name", "Barcode", "Stock", "Price", "Value"]
    rows   = [header]
    for p in products:
        value      = p["stock"] * p["price"]
        stock_cell = str(p["stock"])
        rows.append([
            str(p["id"]),
            Paragraph(p["title"], cell_style),
            p["barcode"],
            stock_cell,
            f"{sym}{p['price']:.2f}",
            f"{sym}{value:.2f}",
        ])

    # Totals row
    rows.append([
        "", Paragraph("<b>TOTAL</b>", cell_style), "",
        str(total_units), "",
        f"{sym}{total_value:.2f}",
    ])

    col_widths = [0.5*inch, 3*inch, 1.2*inch, 0.7*inch, 0.9*inch, 0.9*inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#2980B9")),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  _FONT_BOLD),
        ("FONTNAME",    (0, 1), (-1, -1), _FONT_REGULAR),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#EAF4FB")]),
        ("BACKGROUND",  (0, -1), (-1, -1), colors.HexColor("#ECF0F1")),
        ("FONTNAME",    (0, -1), (-1, -1), _FONT_BOLD),
        ("ALIGN",       (3, 1), (-1, -1), "RIGHT"),
        ("ALIGN",       (0, 0), (0, -1),  "CENTER"),
        ("GRID",        (0, 0), (-1, -1), 0.25, colors.HexColor("#BDC3C7")),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWHEIGHT",   (0, 0), (-1, -1), 18),
    ]))
    story.append(tbl)

    # Footer summary
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph(
        f"Products: <b>{len(products)}</b> &nbsp;&nbsp; "
        f"Total units: <b>{total_units}</b> &nbsp;&nbsp; "
        f"Stock value: <b>{sym}{total_value:.2f}</b>",
        styles["Normal"],
    ))

    doc.build(story)

