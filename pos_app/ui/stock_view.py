"""Stock Management screen — full CRUD, sort, per-column filter, pagination."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import product as product_model
from services import barcode_service, zebra_service, receipt_service
from ui.theme import (
    BG, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    TROW_ALT, TROW_LOW, TROW_WARN, NAV_ACT,
    styled_button, insert_rows, Pager,
)

_COLS    = ("ID", "Title", "Author", "Publisher", "Location", "Store", "Storage", "Price")
_WIDTHS  = (45, 180, 130, 120, 90, 60, 74, 75)
_LEFT    = {"Title", "Author", "Publisher", "Location"}
_STRETCH = {"Title", "Author", "Publisher"}
_HDR_H   = 30
_FLT_H   = 26

_SORT_KEY = {
    "ID":        lambda p: p["id"],
    "Title":     lambda p: (p.get("title") or "").lower(),
    "Author":    lambda p: (p.get("author") or "").lower(),
    "Publisher": lambda p: (p.get("publisher") or "").lower(),
    "Location":  lambda p: (p.get("location") or "").lower(),
    "Storage":   lambda p: p.get("storage") or 0,
    "Store":     lambda p: p["stock"],
    "Price":     lambda p: p["price"],
}


def _darken(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"#{max(0,r-22):02x}{max(0,g-22):02x}{max(0,b-22):02x}"


# ── Product dialog (Add / Edit) ───────────────────────────────────────────────
class ProductDialog(tk.Toplevel):
    def __init__(self, parent, title: str, data: dict = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.result: dict | None = None
        self._data = data or {}
        self._build()
        self.grab_set()
        self.transient(parent)
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _label_entry(self, text: str, row: int, default="") -> tk.StringVar:
        tk.Label(self, text=text, bg=BG, font=("Helvetica", 10),
                 anchor="e").grid(row=row, column=0, sticky="e", padx=12, pady=6)
        var = tk.StringVar(master=self, value=str(default))
        tk.Entry(self, textvariable=var, width=32,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).grid(row=row, column=1, padx=12, pady=6)
        return var

    def _build(self):
        d = self._data
        self._f_title     = self._label_entry("Title:",     0, d.get("title",     ""))
        self._f_author    = self._label_entry("Author:",    1, d.get("author",    ""))
        self._f_publisher = self._label_entry("Publisher:", 2, d.get("publisher", ""))
        self._f_webstore  = self._label_entry("Webstore:",  3, d.get("webstore",  ""))
        self._f_location  = self._label_entry("Location:",  4, d.get("location",  ""))
        self._f_storage   = self._label_entry("Storage:",   5, d.get("storage",   ""))
        self._f_stock     = self._label_entry("Store:",     6, d.get("stock",     0))
        self._f_price     = self._label_entry("Price:",     7, d.get("price",     ""))

        tk.Label(self, text="Barcode:", bg=BG, font=("Helvetica", 10),
                 anchor="e").grid(row=8, column=0, sticky="e", padx=12, pady=6)
        bc_text = d["barcode"] if d.get("barcode") else "Auto-generated on save"
        tk.Label(self, text=bc_text, bg=BG, font=("Helvetica", 10, "italic"),
                 fg=FG_MUTED).grid(row=8, column=1, sticky="w", padx=12)

        row_btn = tk.Frame(self, bg=BG)
        row_btn.grid(row=9, column=0, columnspan=2, pady=12)
        styled_button(row_btn, "Save",   self._save,   bg=BTN_OK).pack(side="left", padx=6)
        styled_button(row_btn, "Cancel", self.destroy, bg=BTN_DNG).pack(side="left", padx=6)

    def _save(self):
        title = self._f_title.get().strip()
        if not title:
            messagebox.showerror("Validation", "Title is required.", parent=self)
            return
        try:
            stock = int(self._f_stock.get())
            if stock < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation", "Stock must be a non-negative integer.",
                                 parent=self)
            return
        try:
            price = float(self._f_price.get())
            if price < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation", "Price must be a non-negative number.",
                                 parent=self)
            return
        storage_raw = self._f_storage.get().strip()
        storage = None
        if storage_raw:
            try:
                storage = int(storage_raw)
            except ValueError:
                messagebox.showerror("Validation", "Storage must be a whole number.",
                                     parent=self)
                return
        self.result = {
            "title":     title,
            "author":    self._f_author.get().strip(),
            "publisher": self._f_publisher.get().strip(),
            "webstore":  self._f_webstore.get().strip(),
            "location":  self._f_location.get().strip(),
            "storage":   storage,
            "stock":     stock,
            "price":     price,
        }
        self.destroy()


# ── Stock Management View ─────────────────────────────────────────────────────
class StockView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._sort_col: str | None = None
        self._sort_asc: bool = True
        self._header_btns:   dict[str, tk.Button] = {}
        self._filter_vars:   dict[str, tk.StringVar] = {}
        self._filter_entries: dict[str, tk.Entry]   = {}
        self._build()
        self.on_show()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # Search bar
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Search:", bg=BG, font=("Helvetica", 10)).pack(side="left")
        self._search_var = tk.StringVar(master=self)
        self._search_var.trace_add("write", self._on_search)
        tk.Entry(top, textvariable=self._search_var, width=30,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).pack(side="left", padx=6)
        styled_button(top, "Clear Filters", self._clear_filters,
                      bg="#95A5A6").pack(side="left", padx=6)

        # Treeview style: no border so column x=0 matches overlay x=0
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Stock.Treeview",
                        background="white", fieldbackground="white",
                        rowheight=26, font=("Helvetica", 10),
                        borderwidth=0, relief="flat")
        style.layout("Stock.Treeview", [
            ("Stock.Treeview.treearea", {"sticky": "nswe"})
        ])
        style.map("Stock.Treeview", background=[("selected", NAV_ACT)])

        # Table container
        tbl = tk.Frame(self, bg=BG)
        tbl.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        # Custom header row (buttons positioned by _place_overlay)
        self._hdr_frame = tk.Frame(tbl, bg=HEADER_BG, height=_HDR_H)
        self._hdr_frame.pack(fill="x")
        self._hdr_frame.pack_propagate(False)

        # Filter row (entries positioned by _place_overlay)
        self._flt_frame = tk.Frame(tbl, bg="#D5DBDB", height=_FLT_H)
        self._flt_frame.pack(fill="x")
        self._flt_frame.pack_propagate(False)

        # Pre-create all header buttons and filter entries
        for col in _COLS:
            anchor = "w" if col in _LEFT else "center"
            btn = tk.Button(self._hdr_frame, text=col,
                            bg=HEADER_BG, fg=HEADER_FG,
                            font=("Helvetica", 10, "bold"),
                            relief="flat", anchor=anchor, padx=4,
                            cursor="hand2",
                            command=lambda c=col: self._sort_by(c))
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=_darken(HEADER_BG)))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=HEADER_BG))
            self._header_btns[col] = btn

            var = tk.StringVar(master=self)
            var.trace_add("write", self._on_filter_change)
            self._filter_vars[col] = var
            entry = tk.Entry(self._flt_frame, textvariable=var,
                             font=("Helvetica", 9), relief="solid", bd=1, bg="white")
            self._filter_entries[col] = entry

        # Treeview (show="" → no built-in heading, no border)
        tv_wrap = tk.Frame(tbl, bg=BG)
        tv_wrap.pack(fill="both", expand=True)

        self._tv = ttk.Treeview(tv_wrap, columns=_COLS, show="",
                                style="Stock.Treeview", selectmode="browse")
        for col, w in zip(_COLS, _WIDTHS):
            anchor = "w" if col in _LEFT else "center"
            self._tv.column(col, width=w, minwidth=w, anchor=anchor,
                            stretch=col in _STRETCH)
        self._tv.tag_configure("alt",  background=TROW_ALT)
        self._tv.tag_configure("low",  background=TROW_LOW)
        self._tv.tag_configure("warn", background=TROW_WARN, foreground="white")

        vsb = ttk.Scrollbar(tv_wrap, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        self._tv.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tv.bind("<Double-1>", lambda e: self._edit())
        self._tv.bind("<Configure>", lambda e: self.after_idle(self._place_overlay))

        # Pager
        self._pager = Pager(self, config.PAGE_SIZE, self._refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Action buttons
        bot = tk.Frame(self, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        styled_button(bot, "+ Add Product",      self._add,           bg=BTN_OK   ).pack(side="left", padx=4)
        styled_button(bot, "Edit Selected",      self._edit                        ).pack(side="left", padx=4)
        styled_button(bot, "Delete Selected",    self._delete,        bg=BTN_DNG  ).pack(side="left", padx=4)
        styled_button(bot, "Print Barcode",      self._print_bc,
                      bg="#8E44AD", fg="#1C1C1C"                                   ).pack(side="left", padx=4)
        styled_button(bot, "Print Stock Report", self._print_report,  bg="#E67E22" ).pack(side="left", padx=4)

    def _place_overlay(self):
        """Position header buttons and filter entries to match actual treeview column widths."""
        try:
            self._tv.update_idletasks()
            x = 0
            for col in _COLS:
                w = self._tv.column(col, "width")
                self._header_btns[col].place(x=x, y=0, width=w, height=_HDR_H)
                self._filter_entries[col].place(x=x, y=2, width=w, height=_FLT_H - 4)
                x += w
        except tk.TclError:
            pass

    # ── Data refresh ──────────────────────────────────────────────────────────
    def on_show(self):
        self._refresh()
        self.after(50, self._place_overlay)

    def _on_search(self, *_):
        self._pager.reset()
        self._refresh()

    def _on_filter_change(self, *_):
        self._pager.reset()
        self._refresh()

    def _refresh(self, *_):
        q = self._search_var.get().strip()
        rows_data = product_model.search(q) if q else product_model.get_all()

        # Per-column filters
        active = {col: var.get().strip().lower()
                  for col, var in self._filter_vars.items()
                  if var.get().strip()}
        if active:
            def _matches(p: dict) -> bool:
                vals = {
                    "ID":        str(p["id"]),
                    "Title":     (p.get("title") or "").lower(),
                    "Author":    (p.get("author") or "").lower(),
                    "Publisher": (p.get("publisher") or "").lower(),
                    "Location":  (p.get("location") or "").lower(),
                    "Storage":   str(p["storage"]) if p.get("storage") is not None else "",
                    "Store":     str(p["stock"]),
                    "Price":     f"{p['price']:.2f}",
                }
                return all(f in vals.get(col, "") for col, f in active.items())
            rows_data = [p for p in rows_data if _matches(p)]

        # Sort
        if self._sort_col and self._sort_col in _SORT_KEY:
            rows_data = sorted(rows_data,
                               key=_SORT_KEY[self._sort_col],
                               reverse=not self._sort_asc)

        # Build display rows with stock highlighting
        sym = config.CURRENCY_SYMBOL
        display_rows: list[tuple] = []
        warn_indices: set[int] = set()
        low_indices:  set[int] = set()
        for p in rows_data:
            stock = p["stock"]
            if stock == 0:
                stock_cell = f"⚠ {stock}"
                warn_indices.add(len(display_rows))
            elif stock <= config.LOW_STOCK_THRESHOLD:
                stock_cell = f"⚠ {stock}"
                low_indices.add(len(display_rows))
            else:
                stock_cell = str(stock)
            display_rows.append((
                p["id"], p["title"],
                p.get("author") or "—", p.get("publisher") or "—",
                p.get("location") or "—",
                stock_cell,
                str(p["storage"]) if p.get("storage") is not None else "—",
                f"{sym}{p['price']:.2f}",
            ))

        self._pager.set_total(len(display_rows))
        page_start = (self._pager._page - 1) * self._pager.page_size
        page_rows  = self._pager.slice(display_rows)
        page_warns = {i - page_start for i in warn_indices
                      if page_start <= i < page_start + self._pager.page_size}
        page_lows  = {i - page_start for i in low_indices
                      if page_start <= i < page_start + self._pager.page_size}
        insert_rows(self._tv, page_rows, warn_indices=page_warns, low_indices=page_lows)

    # ── Sort ──────────────────────────────────────────────────────────────────
    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._pager.reset()
        self._refresh()
        for c, btn in self._header_btns.items():
            arrow = (" ▲" if self._sort_asc else " ▼") if c == self._sort_col else ""
            btn.config(text=c + arrow)

    def _clear_filters(self):
        self._search_var.set("")
        for var in self._filter_vars.values():
            var.set("")
        self._sort_col = None
        self._sort_asc = True
        for c, btn in self._header_btns.items():
            btn.config(text=c)
        self._pager.reset()
        self._refresh()

    # ── Selection helper ──────────────────────────────────────────────────────
    def _selected_product(self) -> dict | None:
        sel = self._tv.selection()
        if not sel:
            messagebox.showwarning("Selection", "Please select a product first.")
            return None
        pid = int(self._tv.item(sel[0])["values"][0])
        return product_model.get_by_id(pid)

    # ── CRUD actions ──────────────────────────────────────────────────────────
    def _add(self):
        dlg = ProductDialog(self, "Add Product")
        self.wait_window(dlg)
        if dlg.result:
            r = dlg.result
            product_model.create(
                r["title"], r["stock"], r["price"],
                author=r["author"], publisher=r["publisher"],
                webstore=r["webstore"], location=r["location"],
                storage=r["storage"],
            )
            self._refresh()

    def _edit(self):
        p = self._selected_product()
        if not p:
            return
        dlg = ProductDialog(self, "Edit Product", p)
        self.wait_window(dlg)
        if dlg.result:
            r = dlg.result
            product_model.update(
                p["id"], r["title"], r["stock"], r["price"],
                author=r["author"], publisher=r["publisher"],
                webstore=r["webstore"], location=r["location"],
                storage=r["storage"],
            )
            self._refresh()

    def _delete(self):
        p = self._selected_product()
        if not p:
            return
        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete '{p['title']}'?\nThis cannot be undone."):
            return
        product_model.delete(p["id"])
        self._refresh()

    # ── Print actions ─────────────────────────────────────────────────────────
    def _print_bc(self):
        p = self._selected_product()
        if not p:
            return
        self._show_print_dialog(p)

    def _show_print_dialog(self, p: dict):
        win = tk.Toplevel(self)
        win.title("Print Barcode")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Print Barcode Label",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 12, "bold"), pady=8).pack(fill="x")

        info = tk.Frame(win, bg=BG)
        info.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(info, text=f"Title  : {p['title']}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        tk.Label(info, text=f"Barcode : {p['barcode']}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w", pady=(2, 0))

        bc_width = barcode_service.barcode_pixel_width(p["barcode"], scale=2)
        canvas = tk.Canvas(win, bg="white", width=bc_width + 20,
                           height=90, highlightthickness=1,
                           highlightbackground=BORDER)
        canvas.pack(padx=16, pady=10)
        barcode_service.draw_on_canvas(canvas, p["barcode"],
                                       x=10, y=10, bar_height=60, scale=2)
        canvas.create_text(bc_width // 2 + 10, 78,
                           text=p["barcode"], font=("Courier", 9))

        status = tk.Label(win, text="", bg=BG, font=("Helvetica", 9), fg=FG_MUTED)
        status.pack(pady=(0, 4))

        def do_print():
            zpl = zebra_service.build_product_zpl(p["title"], p["barcode"])
            try:
                zebra_service.print_label_usb(zpl)
                status.config(text="✓ Sent to printer.", fg="#27AE60")
            except OSError as e:
                status.config(text=f"Printer error: {e}", fg="#E74C3C")

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=(4, 12))
        styled_button(btn_row, "Print", do_print,    bg=BTN_OK ).pack(side="left", padx=6)
        styled_button(btn_row, "Close", win.destroy, bg=BTN_DNG).pack(side="left", padx=6)

        win.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width()  - win.winfo_width())  // 2
        py = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{px}+{py}")

    def _print_report(self):
        try:
            path = receipt_service.build_stock_report_pdf(product_model.get_all())
            messagebox.showinfo("Stock Report", f"Report saved and opened:\n{path}")
        except Exception as exc:
            messagebox.showerror("Report Error", str(exc))
