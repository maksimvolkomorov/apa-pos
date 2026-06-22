"""Stock Management screen — full CRUD, universal search, pagination."""
import tkinter as tk
from tkinter import messagebox

import config
from models import product as product_model
from services import barcode_service, zebra_service, receipt_service
from ui.theme import (
    BG, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    styled_button, make_treeview, insert_rows, Pager,
)


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
        # centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _label_entry(self, text: str, row: int, default="") -> tk.StringVar:
        tk.Label(self, text=text, bg=BG, font=("Helvetica", 10),
                 anchor="e").grid(row=row, column=0, sticky="e", padx=12, pady=6)
        var = tk.StringVar(master=self, value=str(default))
        tk.Entry(self, textvariable=var, width=28,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).grid(row=row, column=1, padx=12, pady=6)
        return var

    def _build(self):
        d = self._data
        self._f_name  = self._label_entry("Name:",  0, d.get("name",  ""))
        self._f_stock = self._label_entry("Stock:", 1, d.get("stock", 0))
        self._f_price = self._label_entry("Price:", 2, d.get("price", ""))

        # Barcode: editable only on add (auto-generated); read-only on edit
        tk.Label(self, text="Barcode:", bg=BG, font=("Helvetica", 10),
                 anchor="e").grid(row=3, column=0, sticky="e", padx=12, pady=6)
        if d.get("barcode"):
            tk.Label(self, text=d["barcode"], bg=BG,
                     font=("Helvetica", 10, "italic"),
                     fg=FG_MUTED).grid(row=3, column=1, sticky="w", padx=12)
        else:
            tk.Label(self, text="Auto-generated on save", bg=BG,
                     font=("Helvetica", 10, "italic"),
                     fg=FG_MUTED).grid(row=3, column=1, sticky="w", padx=12)

        row_btn = tk.Frame(self, bg=BG)
        row_btn.grid(row=4, column=0, columnspan=2, pady=12)
        styled_button(row_btn, "Save",   self._save,   bg=BTN_OK).pack(side="left", padx=6)
        styled_button(row_btn, "Cancel", self.destroy, bg=BTN_DNG).pack(side="left", padx=6)

    def _save(self):
        name = self._f_name.get().strip()
        if not name:
            messagebox.showerror("Validation", "Name is required.", parent=self)
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
        self.result = {"name": name, "stock": stock, "price": price}
        self.destroy()


# ── Stock Management View ─────────────────────────────────────────────────────
class StockView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
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
        tk.Entry(top, textvariable=self._search_var, width=36,
                 font=("Helvetica", 10), relief="solid", bd=1
                 ).pack(side="left", padx=6)
        styled_button(top, "Search", self._refresh).pack(side="left", padx=6)

        # Table
        cols   = ("ID", "Name", "Barcode", "Stock", "Price")
        widths = (50, 220, 130, 90, 100)
        tv_frame, self._tv = make_treeview(self, cols, widths,
                                           left_cols=("Name", "Price"),
                                           right_cols=())
        tv_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._tv.bind("<Double-1>", lambda e: self._edit())

        # Pager
        self._pager = Pager(self, config.PAGE_SIZE, self._refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Action buttons
        bot = tk.Frame(self, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        styled_button(bot, "+ Add Product",    self._add,          bg=BTN_OK).pack(side="left", padx=4)
        styled_button(bot, "Edit Selected",    self._edit                    ).pack(side="left", padx=4)
        styled_button(bot, "Delete Selected",  self._delete,       bg=BTN_DNG).pack(side="left", padx=4)
        styled_button(bot, "Print Barcode",    self._print_bc,
                      bg="#8E44AD", fg="#1C1C1C").pack(side="left", padx=4)
        styled_button(bot, "Print Stock Report", self._print_report,
                      bg="#E67E22").pack(side="left", padx=4)

    # ── Data refresh ──────────────────────────────────────────────────────────
    def on_show(self):
        self._refresh()

    def _on_search(self, *_):
        self._pager.reset()
        self._refresh()

    def _refresh(self, *_):
        q = self._search_var.get().strip()
        rows_data = product_model.search(q) if q else product_model.get_all()

        display_rows = []
        warn_indices: set[int] = set()
        for p in rows_data:
            stock_cell = f"⚠ {p['stock']}" if p["stock"] == 0 else str(p["stock"])
            display_rows.append((
                p["id"], p["name"], p["barcode"],
                stock_cell,
                f"{config.CURRENCY_SYMBOL}{p['price']:.2f}",
            ))
            if p["stock"] == 0:
                warn_indices.add(len(display_rows) - 1)

        self._pager.set_total(len(display_rows))
        page_rows = self._pager.slice(display_rows)

        # warn_indices relative to the page slice
        page_start = (self._pager._page - 1) * self._pager.page_size
        page_warns = {i - page_start for i in warn_indices
                      if page_start <= i < page_start + self._pager.page_size}
        insert_rows(self._tv, page_rows, warn_indices=page_warns)

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
            product_model.create(
                dlg.result["name"], dlg.result["stock"], dlg.result["price"]
            )
            self._refresh()

    def _edit(self):
        p = self._selected_product()
        if not p:
            return
        dlg = ProductDialog(self, "Edit Product", p)
        self.wait_window(dlg)
        if dlg.result:
            product_model.update(
                p["id"], dlg.result["name"], dlg.result["stock"], dlg.result["price"]
            )
            self._refresh()

    def _delete(self):
        p = self._selected_product()
        if not p:
            return
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete '{p['name']}'?\nThis cannot be undone.",
        ):
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
        tk.Label(info, text=f"Product : {p['name']}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        tk.Label(info, text=f"Barcode : {p['barcode']}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w", pady=(2, 0))

        # Live barcode preview on canvas
        bc_width = barcode_service.barcode_pixel_width(p["barcode"], scale=2)
        canvas = tk.Canvas(win, bg="white", width=bc_width + 20,
                           height=90, highlightthickness=1,
                           highlightbackground=BORDER)
        canvas.pack(padx=16, pady=10)
        barcode_service.draw_on_canvas(canvas, p["barcode"],
                                       x=10, y=10, bar_height=60, scale=2)
        canvas.create_text(bc_width // 2 + 10, 78,
                           text=p["barcode"], font=("Courier", 9))

        # Status label
        status = tk.Label(win, text="", bg=BG, font=("Helvetica", 9),
                          fg=FG_MUTED)
        status.pack(pady=(0, 4))

        def do_print():
            zpl = zebra_service.build_product_zpl(p["name"], p["barcode"])
            try:
                zebra_service.print_label_usb(zpl)
                status.config(text="✓ Sent to printer.", fg="#27AE60")
            except OSError as e:
                status.config(
                    text=f"Printer error: {e}", fg="#E74C3C"
                )

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=(4, 12))
        styled_button(btn_row, "Print", do_print, bg=BTN_OK).pack(side="left", padx=6)
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
