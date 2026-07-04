"""Stock Management screen — full CRUD, sort, per-column dropdown filter, pagination."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import product as product_model
from services import barcode_service, zebra_service, receipt_service
from ui.theme import (
    BG, BTN_BG, BTN_FG, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    TROW_ALT, TROW_LOW, TROW_WARN, NAV_ACT,
    styled_button, insert_rows, Pager,
)

_COLS    = ("ID", "Title", "Author", "Publisher", "Location", "Store", "Storage", "Price")
_WIDTHS  = (68, 180, 130, 120, 104, 60, 74, 75)
_LEFT    = {"Title", "Author", "Publisher", "Location"}
_STRETCH = {"Title", "Author", "Publisher"}
_HDR_H   = 30
_FDRP_W  = 20   # width of the ▼ filter button inside each column header

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


# ── Excel-style column filter popup ──────────────────────────────────────────
class ColumnFilterPopup(tk.Toplevel):
    """Borderless checklist popup anchored below a column header filter button."""

    def __init__(self, parent, col: str, all_values: list, selected, on_apply):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=BORDER)
        self._col        = col
        self._all_values = sorted({str(v) for v in all_values if v is not None and str(v)},
                                   key=str.lower)
        self._selected   = set(self._all_values) if selected is None else set(selected)
        self._on_apply   = on_apply
        self._vars: dict[str, tk.BooleanVar] = {}
        self._build()
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_force()

    def _build(self):
        inner = tk.Frame(self, bg="white")
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Search box
        self._search_var = tk.StringVar(master=self)
        self._search_var.trace_add("write", lambda *_: self._filter_list())
        tk.Entry(inner, textvariable=self._search_var,
                 font=("Helvetica", 9), relief="solid", bd=1
                 ).pack(fill="x", padx=4, pady=(4, 2))

        # Select All checkbox
        self._all_var = tk.BooleanVar(master=self,
                                      value=len(self._selected) == len(self._all_values))
        tk.Checkbutton(inner, text="(Select All)", variable=self._all_var,
                       bg="white", font=("Helvetica", 9, "bold"),
                       command=self._toggle_all, anchor="w"
                       ).pack(fill="x", padx=4)

        sep = tk.Frame(inner, bg=BORDER, height=1)
        sep.pack(fill="x", padx=4, pady=(0, 2))

        # Scrollable checklist
        list_wrap = tk.Frame(inner, bg="white")
        list_wrap.pack(fill="both", expand=True, padx=4)
        vsb = ttk.Scrollbar(list_wrap, orient="vertical")
        self._canvas = tk.Canvas(list_wrap, bg="white", yscrollcommand=vsb.set,
                                 highlightthickness=0, height=180)
        vsb.config(command=self._canvas.yview)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._check_frame = tk.Frame(self._canvas, bg="white")
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._check_frame, anchor="nw")
        self._check_frame.bind("<Configure>", self._on_frame_resize)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._populate(self._all_values)

        # OK / Clear / Cancel
        btn_row = tk.Frame(inner, bg="white")
        btn_row.pack(fill="x", padx=4, pady=6)
        tk.Button(btn_row, text="OK",     bg=BTN_OK,  fg=BTN_FG,
                  font=("Helvetica", 9), relief="flat", cursor="hand2",
                  command=self._apply ).pack(side="left", padx=2)
        tk.Button(btn_row, text="Clear",  bg=BTN_BG,  fg=BTN_FG,
                  font=("Helvetica", 9), relief="flat", cursor="hand2",
                  command=self._clear ).pack(side="left", padx=2)
        tk.Button(btn_row, text="Cancel", bg=BTN_DNG, fg=BTN_FG,
                  font=("Helvetica", 9), relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left", padx=2)

    def _on_frame_resize(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self._canvas.itemconfig(self._canvas_win, width=e.width)

    def _populate(self, values: list):
        for w in self._check_frame.winfo_children():
            w.destroy()
        for val in values:
            var = self._vars.setdefault(val, tk.BooleanVar(master=self))
            var.set(val in self._selected)
            tk.Checkbutton(self._check_frame,
                           text=val if val else "(blank)",
                           variable=var, bg="white",
                           font=("Helvetica", 9), anchor="w",
                           command=self._on_check
                           ).pack(fill="x")

    def _visible_values(self) -> list:
        q = self._search_var.get().lower()
        return [v for v in self._all_values if q in v.lower()]

    def _filter_list(self):
        visible = self._visible_values()
        self._populate(visible)
        # Auto-select all visible items; deselect items no longer visible
        for v in self._all_values:
            checked = v in visible
            self._selected.discard(v) if not checked else self._selected.add(v)
            if v in self._vars:
                self._vars[v].set(checked)
        self._all_var.set(False)

    def _toggle_all(self):
        state = self._all_var.get()
        for v in self._visible_values():
            if state:
                self._selected.add(v)
            else:
                self._selected.discard(v)
            if v in self._vars:
                self._vars[v].set(state)

    def _on_check(self):
        for v, var in self._vars.items():
            if var.get():
                self._selected.add(v)
            else:
                self._selected.discard(v)
        visible = self._visible_values()
        self._all_var.set(bool(visible) and all(v in self._selected for v in visible))

    def _apply(self):
        result = None if len(self._selected) >= len(self._all_values) else self._selected
        self._on_apply(result)
        self.destroy()

    def _clear(self):
        self._on_apply(None)
        self.destroy()


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
        w = int(self.winfo_screenwidth() * 0.75)
        h = self.winfo_height()
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")

    def _label_entry(self, text: str, row: int, default="") -> tk.StringVar:
        tk.Label(self, text=text, bg=BG, font=("Helvetica", 10),
                 anchor="e").grid(row=row, column=0, sticky="e", padx=12, pady=6)
        var = tk.StringVar(master=self, value=str(default))
        tk.Entry(self, textvariable=var,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).grid(row=row, column=1, padx=12, pady=6, sticky="ew")
        return var

    def _build(self):
        self.columnconfigure(1, weight=1)
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
        self._header_btns:  dict[str, tk.Button] = {}
        self._filter_btns:  dict[str, tk.Button] = {}
        self._col_filters:  dict[str, set | None] = {}   # None = no filter active
        self._popup: tk.Toplevel | None = None
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
        styled_button(top, "Clear Filters", self._clear_filters).pack(side="left", padx=6)

        # Treeview style
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

        # Custom header row
        self._hdr_frame = tk.Frame(tbl, bg=HEADER_BG, height=_HDR_H)
        self._hdr_frame.pack(fill="x")
        self._hdr_frame.pack_propagate(False)

        # Pre-create sort buttons and filter-dropdown buttons per column
        for col in _COLS:
            anchor = "w" if col in _LEFT else "center"
            sort_btn = tk.Button(self._hdr_frame, text=col,
                                 bg=HEADER_BG, fg=HEADER_FG,
                                 font=("Helvetica", 10, "bold"),
                                 relief="flat", anchor=anchor, padx=4,
                                 cursor="hand2",
                                 command=lambda c=col: self._sort_by(c))
            sort_btn.bind("<Enter>", lambda e, b=sort_btn: b.config(bg=_darken(HEADER_BG)))
            sort_btn.bind("<Leave>", lambda e, b=sort_btn: b.config(bg=HEADER_BG))
            self._header_btns[col] = sort_btn

            flt_btn = tk.Button(self._hdr_frame, text="▼",
                                bg=HEADER_BG, fg=HEADER_FG,
                                font=("Helvetica", 7),
                                relief="flat", cursor="hand2",
                                command=lambda c=col: self._open_filter(c))
            flt_btn.bind("<Enter>", lambda e, b=flt_btn: b.config(bg=_darken(HEADER_BG)))
            flt_btn.bind("<Leave>", lambda e, b=flt_btn: self._restore_filter_btn_bg(b))
            self._filter_btns[col] = flt_btn

        # Treeview (no built-in heading)
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
        styled_button(bot, "+ Add Product",      self._add,          bg=BTN_OK   ).pack(side="left", padx=4)
        self._btn_edit   = styled_button(bot, "Edit Selected",   self._edit,      )
        self._btn_delete = styled_button(bot, "Delete Selected", self._delete,    bg=BTN_DNG)
        self._btn_bc     = styled_button(bot, "Barcode",          self._print_bc,  bg="#8E44AD", fg="#1C1C1C")
        self._btn_edit  .pack(side="left", padx=4)
        self._btn_delete.pack(side="left", padx=4)
        self._btn_bc    .pack(side="left", padx=4)
        styled_button(bot, "Print Stock Report", self._print_report, bg="#E67E22").pack(side="left", padx=4)

        self._selection_btns = [
            (self._btn_edit,   BTN_BG,    BTN_FG),
            (self._btn_delete, BTN_DNG,   BTN_FG),
            (self._btn_bc,     "#8E44AD", "#1C1C1C"),
        ]
        self._tv.bind("<<TreeviewSelect>>", self._on_selection)
        self._on_selection()

    def _place_overlay(self):
        """Position sort buttons and filter-dropdown buttons to match column widths."""
        try:
            self._tv.update_idletasks()
            x = 0
            for col in _COLS:
                w = self._tv.column(col, "width")
                sort_w = max(0, w - _FDRP_W)
                self._header_btns[col].place(x=x,          y=0, width=sort_w, height=_HDR_H)
                self._filter_btns[col].place(x=x + sort_w, y=0, width=_FDRP_W, height=_HDR_H)
                x += w
        except tk.TclError:
            pass

    def _restore_filter_btn_bg(self, btn: tk.Button):
        col = next((c for c, b in self._filter_btns.items() if b is btn), None)
        active = col is not None and self._col_filters.get(col) is not None
        btn.config(bg=_darken(HEADER_BG) if active else HEADER_BG)

    _DISABLED_BG = "#BDBDBD"
    _DISABLED_FG = "#888888"

    def _on_selection(self, *_):
        has_sel = bool(self._tv.selection())
        for btn, active_bg, active_fg in self._selection_btns:
            if has_sel:
                btn.config(state="normal", bg=active_bg, fg=active_fg, cursor="hand2")
            else:
                btn.config(state="disabled", bg=self._DISABLED_BG, fg=self._DISABLED_FG, cursor="")

    # ── Data refresh ──────────────────────────────────────────────────────────
    def on_show(self):
        self._refresh()
        self.after(50, self._place_overlay)

    def _on_search(self, *_):
        self._pager.reset()
        self._refresh()

    def _refresh(self, *_):
        q = self._search_var.get().strip()
        rows_data = product_model.search(q) if q else product_model.get_all()

        # Per-column set filters
        for col, selected in self._col_filters.items():
            if selected is not None:
                rows_data = [p for p in rows_data
                             if self._product_col_value(p, col) in selected]

        # Sort
        if self._sort_col and self._sort_col in _SORT_KEY:
            rows_data = sorted(rows_data,
                               key=_SORT_KEY[self._sort_col],
                               reverse=not self._sort_asc)

        # Build display rows
        sym = config.CURRENCY_SYMBOL
        display_rows: list[tuple] = []
        warn_indices: set[int] = set()
        for p in rows_data:
            stock = p["stock"]
            if stock == 0:
                stock_cell = f"⚠ {stock}"
                warn_indices.add(len(display_rows))
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
        insert_rows(self._tv, page_rows, warn_indices=page_warns)
        self._on_selection()

    # ── Column filter helpers ─────────────────────────────────────────────────
    def _product_col_value(self, p: dict, col: str) -> str:
        sym = config.CURRENCY_SYMBOL
        if col == "ID":        return str(p["id"])
        if col == "Title":     return p.get("title") or ""
        if col == "Author":    return p.get("author") or ""
        if col == "Publisher": return p.get("publisher") or ""
        if col == "Location":  return p.get("location") or ""
        if col == "Store":     return str(p["stock"])
        if col == "Storage":   return str(p["storage"]) if p.get("storage") is not None else ""
        if col == "Price":     return f"{sym}{p['price']:.2f}"
        return ""

    def _open_filter(self, col: str):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()

        q = self._search_var.get().strip()
        all_products = product_model.search(q) if q else product_model.get_all()
        all_values = list({self._product_col_value(p, col) for p in all_products})

        def on_apply(selected):
            if selected is None:
                self._col_filters.pop(col, None)
            else:
                self._col_filters[col] = selected
            self._update_filter_btn(col)
            self._pager.reset()
            self._refresh()

        fbtn = self._filter_btns[col]
        self._hdr_frame.update_idletasks()
        fbtn.update_idletasks()
        ph = 295
        col_idx   = list(_COLS).index(col)
        col_left  = self._header_btns[col].winfo_rootx()
        col_right = fbtn.winfo_rootx() + fbtn.winfo_width()

        if col_idx > 0:
            left_nbr_w = self._tv.column(_COLS[col_idx - 1], "width") // 2
            popup_left = col_left - left_nbr_w
        else:
            popup_left = col_left

        if col_idx < len(_COLS) - 1:
            right_nbr_w = self._tv.column(_COLS[col_idx + 1], "width") // 2
            popup_right = col_right + right_nbr_w
        else:
            popup_right = col_right

        pw = popup_right - popup_left
        sx = popup_left
        sy = self._hdr_frame.winfo_rooty() + _HDR_H

        popup = ColumnFilterPopup(self, col, all_values,
                                  self._col_filters.get(col), on_apply)
        popup.geometry(f"{pw}x{ph}+{sx}+{sy}")
        popup.lift()
        self._popup = popup

        root = self.winfo_toplevel()

        def _dismiss(event):
            try:
                if not popup.winfo_exists():
                    return
                px, py = popup.winfo_rootx(), popup.winfo_rooty()
                pw2, ph2 = popup.winfo_width(), popup.winfo_height()
                if not (px <= event.x_root <= px + pw2 and py <= event.y_root <= py + ph2):
                    popup.destroy()
            except tk.TclError:
                pass

        bind_id = root.bind("<Button-1>", _dismiss, add=True)

        def _on_popup_destroy(e):
            if e.widget is popup:
                try:
                    root.unbind("<Button-1>", bind_id)
                except tk.TclError:
                    pass

        popup.bind("<Destroy>", _on_popup_destroy)

    def _update_filter_btn(self, col: str):
        btn = self._filter_btns[col]
        active = self._col_filters.get(col) is not None
        btn.config(fg="#F0C040" if active else HEADER_FG)

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
        self._col_filters.clear()
        for col in _COLS:
            self._update_filter_btn(col)
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
        win.title("Barcode")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Barcode Label",
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
            try:
                barcode_service.print_barcode_label(
                    p["title"], p["barcode"], p.get("price"))
                status.config(text="✓ Done.", fg="#27AE60")
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
