"""Product Detail page — full attribute view, per-column filtering, and sort."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import product as product_model
from ui.stock_view import ProductDialog
from ui.theme import (
    BG, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG,
    TROW_ALT, TROW_LOW, TROW_WARN, NAV_ACT,
    styled_button, insert_rows, Pager,
)

_COLS    = ("ID", "Title", "Author", "Publisher", "Location", "Barcode", "Stock", "Price")
_WIDTHS  = (45, 180, 130, 120, 100, 110, 60, 75)
_LEFT    = {"Title", "Author", "Publisher", "Location"}
_STRETCH = {"Title", "Author", "Publisher", "Location"}
_HDR_H   = 30
_FLT_H   = 26

_SORT_KEY = {
    "ID":        lambda p: p["id"],
    "Title":     lambda p: (p.get("title") or "").lower(),
    "Author":    lambda p: (p.get("author") or "").lower(),
    "Publisher": lambda p: (p.get("publisher") or "").lower(),
    "Location":  lambda p: (p.get("location") or "").lower(),
    "Barcode":   lambda p: p["barcode"],
    "Stock":     lambda p: p["stock"],
    "Price":     lambda p: p["price"],
}


def _darken(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"#{max(0,r-22):02x}{max(0,g-22):02x}{max(0,b-22):02x}"


class ProductDetailView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._sort_col: str | None = None
        self._sort_asc: bool = True
        self._current_product: dict | None = None
        self._header_btns: dict[str, tk.Button] = {}
        self._filter_vars:   dict[str, tk.StringVar] = {}
        self._filter_entries: dict[str, tk.Entry]   = {}
        self._build()
        self.on_show()

    def on_show(self):
        self._refresh()
        # re-align after the panel becomes visible
        self.after(50, self._place_overlay)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_list_panel()
        self._build_detail_panel()
        self._list_panel.pack(fill="both", expand=True)

    def _build_list_panel(self):
        self._list_panel = tk.Frame(self, bg=BG)

        # Search bar
        top = tk.Frame(self._list_panel, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Search:", bg=BG, font=("Helvetica", 10)).pack(side="left")
        self._search_var = tk.StringVar(master=self)
        self._search_var.trace_add("write", self._on_search)
        tk.Entry(top, textvariable=self._search_var, width=30,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).pack(side="left", padx=6)
        styled_button(top, "Clear Filters", self._clear_filters,
                      bg="#95A5A6").pack(side="left", padx=6)

        # ── Treeview with no border so column x=0 matches overlay x=0 ─────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Detail.Treeview",
                        background="white", fieldbackground="white",
                        rowheight=26, font=("Helvetica", 10),
                        borderwidth=0, relief="flat")
        style.layout("Detail.Treeview", [
            ("Detail.Treeview.treearea", {"sticky": "nswe"})
        ])
        style.map("Detail.Treeview", background=[("selected", NAV_ACT)])

        # Outer frame — header + filter overlay + treeview all share same x=0
        self._tbl = tk.Frame(self._list_panel, bg=BG)
        self._tbl.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        # ── Fixed-height header frame (buttons placed via place() later) ───────
        self._hdr_frame = tk.Frame(self._tbl, bg=HEADER_BG, height=_HDR_H)
        self._hdr_frame.pack(fill="x")
        self._hdr_frame.pack_propagate(False)

        # ── Fixed-height filter frame (entries placed via place() later) ───────
        self._flt_frame = tk.Frame(self._tbl, bg="#D5DBDB", height=_FLT_H)
        self._flt_frame.pack(fill="x")
        self._flt_frame.pack_propagate(False)

        # Pre-create all buttons and entries; position them after rendering
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

        # ── Treeview + scrollbar ──────────────────────────────────────────────
        tv_wrap = tk.Frame(self._tbl, bg=BG)
        tv_wrap.pack(fill="both", expand=True)

        self._tv = ttk.Treeview(tv_wrap, columns=_COLS, show="",
                                style="Detail.Treeview", selectmode="browse")
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

        self._tv.bind("<Double-1>", lambda e: self._view_detail())
        # Re-align header/filter whenever the treeview is resized
        self._tv.bind("<Configure>", lambda e: self.after_idle(self._place_overlay))

        # Pager
        self._pager = Pager(self._list_panel, config.PAGE_SIZE, self._refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Bottom buttons
        bot = tk.Frame(self._list_panel, bg=BG, pady=8)
        bot.pack(fill="x", padx=12, side="bottom")
        styled_button(bot, "View / Edit", self._view_detail,
                      bg=BTN_OK).pack(side="left", padx=4)

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

    def _build_detail_panel(self):
        self._detail_panel = tk.Frame(self, bg=BG)

        hdr = tk.Frame(self._detail_panel, bg=HEADER_BG)
        hdr.pack(fill="x")
        styled_button(hdr, "← Back", self._show_list,
                      bg="#3498DB").pack(side="left", padx=12, pady=8)
        self._detail_title_lbl = tk.Label(
            hdr, text="", bg=HEADER_BG, fg=HEADER_FG,
            font=("Helvetica", 12, "bold"))
        self._detail_title_lbl.pack(side="left", padx=8)

        fields_outer = tk.Frame(self._detail_panel, bg=BG)
        fields_outer.pack(fill="both", expand=True, padx=30, pady=20)

        self._field_vars: dict[str, tk.StringVar] = {}
        for row_i, (label, key) in enumerate([
            ("Title",     "title"),
            ("Author",    "author"),
            ("Publisher", "publisher"),
            ("Webstore",  "webstore"),
            ("Location",  "location"),
            ("Barcode",   "barcode"),
            ("Stock",     "stock"),
            ("Price",     "price"),
        ]):
            tk.Label(fields_outer, text=f"{label}:", bg=BG,
                     font=("Helvetica", 11, "bold"), anchor="e", width=12
                     ).grid(row=row_i, column=0, sticky="e", pady=8, padx=(0, 16))
            var = tk.StringVar(master=self)
            self._field_vars[key] = var
            tk.Label(fields_outer, textvariable=var, bg=BG,
                     font=("Helvetica", 11), anchor="w", wraplength=500
                     ).grid(row=row_i, column=1, sticky="w", pady=8)

        tk.Frame(self._detail_panel, bg=BORDER, height=1
                 ).pack(fill="x", padx=14, side="bottom")
        bot = tk.Frame(self._detail_panel, bg=BG)
        bot.pack(fill="x", padx=14, pady=10, side="bottom")
        styled_button(bot, "Edit",   self._edit_current,   bg=BTN_OK ).pack(side="left", padx=4)
        styled_button(bot, "Delete", self._delete_current, bg=BTN_DNG).pack(side="left", padx=4)

    # ── Panel switching ───────────────────────────────────────────────────────
    def _show_list(self):
        self._current_product = None
        self._detail_panel.pack_forget()
        self._list_panel.pack(fill="both", expand=True)
        self._refresh()
        self.after(50, self._place_overlay)

    def _show_detail(self):
        self._list_panel.pack_forget()
        self._detail_panel.pack(fill="both", expand=True)

    # ── Sort ─────────────────────────────────────────────────────────────────
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

    # ── Filter / search ───────────────────────────────────────────────────────
    def _on_search(self, *_):
        self._pager.reset()
        self._refresh()

    def _on_filter_change(self, *_):
        self._pager.reset()
        self._refresh()

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

    # ── Data ─────────────────────────────────────────────────────────────────
    def _refresh(self, *_):
        q = self._search_var.get().strip()
        rows_data = product_model.search(q) if q else product_model.get_all()

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
                    "Barcode":   p["barcode"].lower(),
                    "Stock":     str(p["stock"]),
                    "Price":     f"{p['price']:.2f}",
                }
                return all(f in vals.get(col, "") for col, f in active.items())
            rows_data = [p for p in rows_data if _matches(p)]

        if self._sort_col and self._sort_col in _SORT_KEY:
            rows_data = sorted(rows_data,
                               key=_SORT_KEY[self._sort_col],
                               reverse=not self._sort_asc)

        sym = config.CURRENCY_SYMBOL
        rows = [(p["id"], p["title"],
                 p.get("author") or "—", p.get("publisher") or "—",
                 p.get("location") or "—", p["barcode"],
                 str(p["stock"]), f"{sym}{p['price']:.2f}")
                for p in rows_data]

        self._pager.set_total(len(rows))
        insert_rows(self._tv, self._pager.slice(rows))

    def _selected_id(self) -> int | None:
        sel = self._tv.selection()
        if not sel:
            messagebox.showwarning("Selection", "Please select a product first.")
            return None
        return int(self._tv.item(sel[0])["values"][0])

    def _view_detail(self):
        pid = self._selected_id()
        if pid is None:
            return
        p = product_model.get_by_id(pid)
        if not p:
            return
        self._load_detail(p)
        self._show_detail()

    def _load_detail(self, p: dict):
        self._current_product = p
        sym = config.CURRENCY_SYMBOL
        self._detail_title_lbl.config(text=p["title"])
        self._field_vars["title"].set(p["title"])
        self._field_vars["author"].set(p.get("author") or "—")
        self._field_vars["publisher"].set(p.get("publisher") or "—")
        self._field_vars["webstore"].set(p.get("webstore") or "—")
        self._field_vars["location"].set(p.get("location") or "—")
        self._field_vars["barcode"].set(p["barcode"])
        self._field_vars["stock"].set(str(p["stock"]))
        self._field_vars["price"].set(f"{sym}{p['price']:.2f}")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _edit_current(self):
        if not self._current_product:
            return
        p = self._current_product
        dlg = ProductDialog(self, "Edit Product", p)
        self.wait_window(dlg)
        if dlg.result:
            r = dlg.result
            updated = product_model.update(
                p["id"], r["title"], r["stock"], r["price"],
                author=r["author"], publisher=r["publisher"],
                webstore=r["webstore"], location=r["location"],
            )
            self._load_detail(updated)

    def _delete_current(self):
        if not self._current_product:
            return
        p = self._current_product
        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete '{p['title']}'?\nThis cannot be undone."):
            return
        product_model.delete(p["id"])
        self._show_list()
