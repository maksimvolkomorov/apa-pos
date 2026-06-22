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


# ── Public API ────────────────────────────────────────────────────────────────

def print_receipt(order: dict, items: list[dict]) -> None:
    """
    Dispatch a receipt according to config.RECEIPT_MODE.
    Raises OSError / IOError on failure so the caller can show a warning.
    """
    mode = config.RECEIPT_MODE
    if mode == "zebra":
        from services.zebra_service import print_label_usb
        zpl = build_receipt_zpl(order, items)
        print_label_usb(zpl)

    elif mode == "pdf":
        os.makedirs(config.RECEIPT_OUTPUT_DIR, exist_ok=True)
        requested = os.path.join(
            config.RECEIPT_OUTPUT_DIR,
            f"receipt_{order['id']}.pdf",
        )
        actual_path = build_receipt_pdf(order, items, requested)
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

    # Line items
    for item in items:
        name     = item["product_name"][:22]
        qty      = item["quantity"]
        price    = item["quantity"] * item["unit_price"]
        content  = f"{name:<22} x{qty:<2} {sym}{price:>7.2f}"
        cmd, y = text(y, content)
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
        name  = item["product_name"]
        qty   = item["quantity"]
        price = item["quantity"] * item["unit_price"]
        left  = f"  {name} x{qty}"
        right = f"{sym}{price:.2f}"
        gap   = w - len(left) - len(right)
        receipt_lines.append(left + " " * max(gap, 1) + right)

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
    n_lines  = 8 + len(items)
    page_h   = (n_lines * line_h + 60) * 1.0

    c   = rl_canvas.Canvas(path, pagesize=(page_w, page_h))
    y   = page_h - 20

    def draw(txt: str, size: int = 9, bold: bool = False, centre: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
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
        name  = item["product_name"]
        qty   = item["quantity"]
        price = item["quantity"] * item["unit_price"]
        c.setFont("Helvetica", 9)
        c.drawString(margin, y, f"{name} x{qty}")
        c.drawRightString(page_w - margin, y, f"{sym}{price:.2f}")
        y -= line_h

    hline()
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, "Subtotal")
    c.drawRightString(page_w - margin, y, f"{sym}{subtotal:.2f}")
    y -= line_h
    c.drawString(margin, y, "Sales Tax")
    c.drawRightString(page_w - margin, y, f"{sym}{tax:.2f}")
    y -= line_h
    hline(thick=1.5)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "TOTAL")
    c.drawRightString(page_w - margin, y, f"{sym}{total:.2f}")
    y -= line_h
    hline()
    draw("Thank you!", size=9, centre=True)

    c.save()


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
        stock_cell = f"⚠ {p['stock']}" if p["stock"] == 0 else str(p["stock"])
        lines.append(
            f"{p['id']:<6} {p['name'][:28]:<28} {p['barcode']:<12}"
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

    sym         = config.CURRENCY_SYMBOL
    total_units = sum(p["stock"] for p in products)
    total_value = sum(p["stock"] * p["price"] for p in products)

    doc    = SimpleDocTemplate(path, pagesize=landscape(LETTER),
                               leftMargin=0.5*inch, rightMargin=0.5*inch,
                               topMargin=0.5*inch,  bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story  = []

    # Header
    story.append(Paragraph("STOCK REPORT", styles["Title"]))
    story.append(Paragraph(config.STORE_NAME, styles["Normal"]))
    story.append(Paragraph(_fmt_dt(now.strftime("%Y-%m-%d %H:%M")),
                            styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    # Table
    header = ["ID", "Name", "Barcode", "Stock", "Price", "Value"]
    rows   = [header]
    for p in products:
        value      = p["stock"] * p["price"]
        stock_cell = f"⚠ {p['stock']}" if p["stock"] == 0 else str(p["stock"])
        rows.append([
            str(p["id"]),
            p["name"],
            p["barcode"],
            stock_cell,
            f"{sym}{p['price']:.2f}",
            f"{sym}{value:.2f}",
        ])

    # Totals row
    rows.append([
        "", "TOTAL", "",
        str(total_units), "",
        f"{sym}{total_value:.2f}",
    ])

    col_widths = [0.5*inch, 3*inch, 1.2*inch, 0.7*inch, 0.9*inch, 0.9*inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#2980B9")),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#EAF4FB")]),
        ("BACKGROUND",  (0, -1), (-1, -1), colors.HexColor("#ECF0F1")),
        ("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold"),
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

