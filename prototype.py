"""
POS Application — Clickable GUI Prototype
In-memory mock data; no database or printer required.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime

# ── Palette ──────────────────────────────────────────────────────────────────
BG        = "#F5F5F5"
NAV_BG    = "#2C3E50"
NAV_FG    = "#ECF0F1"
NAV_ACT   = "#1ABC9C"
BTN_BG    = "#3498DB"
BTN_FG    = "#1C1C1C"
BTN_DNG   = "#E74C3C"
BTN_OK    = "#2ECC71"
TROW_ALT  = "#EAF4FB"
HEADER_BG = "#2980B9"
HEADER_FG = "#FFFFFF"
BORDER    = "#BDC3C7"

# ── Mock data ─────────────────────────────────────────────────────────────────
_next_product_id = 6
PRODUCTS = [
    {"id": 1, "name": "Apple Juice 1L",    "barcode": "100001", "stock": 50, "price": 3.50},
    {"id": 2, "name": "Whole Milk 2L",     "barcode": "100002", "stock": 30, "price": 2.99},
    {"id": 3, "name": "Sourdough Bread",   "barcode": "100003", "stock": 20, "price": 4.75},
    {"id": 4, "name": "Cheddar Cheese",    "barcode": "100004", "stock": 15, "price": 6.49},
    {"id": 5, "name": "Organic Eggs x12", "barcode": "100005", "stock":  8, "price": 5.99},
]

_next_order_id = 43
ORDERS = [
    {"id": 42, "created_at": "2026-06-21 14:30", "total": 34.97,
     "items": [{"name": "Apple Juice 1L",  "qty": 2, "unit_price": 3.50},
               {"name": "Whole Milk 2L",   "qty": 1, "unit_price": 2.99},
               {"name": "Sourdough Bread", "qty": 2, "unit_price": 4.75}]},
    {"id": 41, "created_at": "2026-06-21 11:05", "total": 6.49,
     "items": [{"name": "Cheddar Cheese",  "qty": 1, "unit_price": 6.49}]},
    {"id": 40, "created_at": "2026-06-20 16:20", "total": 17.46,
     "items": [{"name": "Organic Eggs x12", "qty": 1, "unit_price": 5.99},
               {"name": "Apple Juice 1L",   "qty": 2, "unit_price": 3.50},
               {"name": "Whole Milk 2L",    "qty": 1, "unit_price": 2.99}]},
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def styled_button(parent, text, command, bg=BTN_BG, fg=BTN_FG, **kw):
    b = tk.Button(parent, text=text, command=command,
                  bg=bg, fg=fg, relief="flat", padx=10, pady=4,
                  font=("Helvetica", 10), cursor="hand2", **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_darken(bg)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def _darken(hex_color):
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r, g, b = max(0, r - 20), max(0, g - 20), max(0, b - 20)
    return f"#{r:02x}{g:02x}{b:02x}"

def make_treeview(parent, columns, col_widths, height=12):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("POS.Treeview",
                    background="white", fieldbackground="white",
                    rowheight=26, font=("Helvetica", 10))
    style.configure("POS.Treeview.Heading",
                    background=HEADER_BG, foreground=HEADER_FG,
                    font=("Helvetica", 10, "bold"), relief="flat")
    style.map("POS.Treeview", background=[("selected", NAV_ACT)])

    frame = tk.Frame(parent, bg=BG)
    tv = ttk.Treeview(frame, columns=columns, show="headings",
                      height=height, style="POS.Treeview",
                      selectmode="browse")
    for col, w in zip(columns, col_widths):
        tv.heading(col, text=col)
        tv.column(col, width=w, anchor="center")
    tv.tag_configure("alt", background=TROW_ALT)

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=vsb.set)
    tv.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    return frame, tv

def insert_rows(tv, rows):
    tv.delete(*tv.get_children())
    for i, row in enumerate(rows):
        tag = "alt" if i % 2 else ""
        tv.insert("", "end", values=row, tags=(tag,))


# ── Pagination control ────────────────────────────────────────────────────────
class Pager(tk.Frame):
    PAGE_SIZE = 15

    def __init__(self, parent, on_change):
        super().__init__(parent, bg=BG)
        self._page = 1
        self._total = 0
        self._on_change = on_change
        self._prev_btn = styled_button(self, "← Prev", self._prev)
        self._prev_btn.pack(side="left", padx=4)
        self._label = tk.Label(self, text="Page 1 of 1", bg=BG,
                               font=("Helvetica", 10))
        self._label.pack(side="left", padx=10)
        self._next_btn = styled_button(self, "Next →", self._next)
        self._next_btn.pack(side="left", padx=4)

    def reset(self):
        self._page = 1

    def set_total(self, total):
        self._total = total
        pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._page = min(self._page, pages)
        self._label.config(text=f"Page {self._page} of {pages}")
        self._prev_btn.config(state="normal" if self._page > 1 else "disabled")
        self._next_btn.config(state="normal" if self._page < pages else "disabled")

    def slice(self, rows):
        start = (self._page - 1) * self.PAGE_SIZE
        return rows[start:start + self.PAGE_SIZE]

    def _prev(self):
        if self._page > 1:
            self._page -= 1
            self._on_change()

    def _next(self):
        pages = max(1, (self._total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._page < pages:
            self._page += 1
            self._on_change()


class ProductDialog(tk.Toplevel):
    def __init__(self, parent, title="Add Product", data=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.result = None
        self._build(data or {})
        self.grab_set()
        self.transient(parent)

    def _field(self, label, row, default=""):
        tk.Label(self, text=label, bg=BG, font=("Helvetica", 10)).grid(
            row=row, column=0, sticky="e", padx=12, pady=6)
        var = tk.StringVar(master=self, value=str(default))
        ent = tk.Entry(self, textvariable=var, width=28,
                       font=("Helvetica", 10), relief="solid", bd=1)
        ent.grid(row=row, column=1, padx=12, pady=6)
        return var

    def _build(self, data):
        self._f_name    = self._field("Name:",    0, data.get("name", ""))
        self._f_barcode = self._field("Barcode:", 1, data.get("barcode", ""))
        self._f_stock   = self._field("Stock:",   2, data.get("stock", 0))
        self._f_price   = self._field("Price:",   3, data.get("price", ""))

        row_btn = tk.Frame(self, bg=BG)
        row_btn.grid(row=4, column=0, columnspan=2, pady=12)
        styled_button(row_btn, "Save", self._save, bg=BTN_OK).pack(side="left", padx=6)
        styled_button(row_btn, "Cancel", self.destroy, bg=BTN_DNG).pack(side="left", padx=6)

    def _save(self):
        name    = self._f_name.get().strip()
        barcode = self._f_barcode.get().strip()
        try:
            stock = int(self._f_stock.get())
            price = float(self._f_price.get())
        except ValueError:
            messagebox.showerror("Validation", "Stock must be integer; Price must be number.", parent=self)
            return
        if not name or not barcode:
            messagebox.showerror("Validation", "Name and Barcode are required.", parent=self)
            return
        self.result = {"name": name, "barcode": barcode, "stock": stock, "price": price}
        self.destroy()


# ── Stock Management View ─────────────────────────────────────────────────────
class StockView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()
        self.refresh()

    def _build(self):
        # Search bar
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Search:", bg=BG, font=("Helvetica", 10)).pack(side="left")
        self._search_var = tk.StringVar(master=self)
        self._search_var.trace_add("write", self._on_search)
        tk.Entry(top, textvariable=self._search_var, width=36,
                 font=("Helvetica", 10), relief="solid", bd=1).pack(side="left", padx=6)
        styled_button(top, "Search", self.refresh).pack(side="left", padx=6)

        # Table
        cols   = ("ID", "Name", "Barcode", "Stock", "Price")
        widths = (50, 220, 120, 80, 100)
        tv_frame, self._tv = make_treeview(self, cols, widths)
        tv_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._tv.bind("<Double-1>", lambda e: self._edit())

        # Pagination
        self._pager = Pager(self, self.refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Action buttons
        bot = tk.Frame(self, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        styled_button(bot, "+ Add Product",    self._add,    bg=BTN_OK).pack(side="left", padx=4)
        styled_button(bot, "Edit Selected",    self._edit                ).pack(side="left", padx=4)
        styled_button(bot, "Delete Selected",  self._delete, bg=BTN_DNG ).pack(side="left", padx=4)
        styled_button(bot, "Print Barcode",    self._print_bc, bg="#8E44AD", fg="#1C1C1C").pack(side="left", padx=4)
        styled_button(bot, "Print Stock Report", self._print_report, bg="#E67E22").pack(side="left", padx=4)

    def _on_search(self, *_):
        self._pager.reset()
        self.refresh()

    def refresh(self, *_):
        q = self._search_var.get().strip().lower()
        rows = []
        for p in PRODUCTS:
            if q and q not in p["name"].lower() and q not in p["barcode"].lower():
                continue
            rows.append((p["id"], p["name"], p["barcode"], p["stock"], f"${p['price']:.2f}"))
        self._pager.set_total(len(rows))
        insert_rows(self._tv, self._pager.slice(rows))

    def _selected_product(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showwarning("Selection", "Please select a product first.")
            return None
        pid = int(self._tv.item(sel[0])["values"][0])
        return next((p for p in PRODUCTS if p["id"] == pid), None)

    def _add(self):
        global _next_product_id
        dlg = ProductDialog(self, "Add Product")
        self.wait_window(dlg)
        if dlg.result:
            # check duplicate barcode
            if any(p["barcode"] == dlg.result["barcode"] for p in PRODUCTS):
                messagebox.showerror("Duplicate", "A product with that barcode already exists.")
                return
            dlg.result["id"] = _next_product_id
            _next_product_id += 1
            PRODUCTS.append(dlg.result)
            self.refresh()

    def _edit(self):
        p = self._selected_product()
        if not p:
            return
        dlg = ProductDialog(self, "Edit Product", p)
        self.wait_window(dlg)
        if dlg.result:
            p.update(dlg.result)
            self.refresh()

    def _delete(self):
        p = self._selected_product()
        if not p:
            return
        if messagebox.askyesno("Confirm Delete",
                               f"Delete '{p['name']}'?\nThis cannot be undone."):
            PRODUCTS.remove(p)
            self.refresh()

    def _print_bc(self):
        p = self._selected_product()
        if not p:
            return
        messagebox.showinfo("Print Barcode",
                            f"[PROTOTYPE]\nSending ZPL label to Zebra printer…\n\n"
                            f"Product : {p['name']}\n"
                            f"Barcode : {p['barcode']}")

    def _print_report(self):
        win = tk.Toplevel(self)
        win.title("Stock Report")
        win.configure(bg=BG)
        win.resizable(True, True)
        win.geometry("560x480")
        win.transient(self)
        win.grab_set()

        # Header
        tk.Label(win, text="STOCK REPORT",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 13, "bold"), pady=10).pack(fill="x")
        tk.Label(win, text=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                 bg=BG, font=("Helvetica", 9), fg="#7F8C8D").pack(anchor="e", padx=12)

        # Report table
        cols   = ("ID", "Name", "Barcode", "Stock", "Price", "Value")
        widths = (40, 180, 100, 60, 80, 80)
        tv_frame, tv = make_treeview(win, cols, widths, height=14)
        tv_frame.pack(fill="both", expand=True, padx=12, pady=8)

        total_items = 0
        total_value = 0.0
        for i, p in enumerate(sorted(PRODUCTS, key=lambda x: x["name"])):
            value = p["stock"] * p["price"]
            total_items += p["stock"]
            total_value += value
            tag = "alt" if i % 2 else ""
            tv.insert("", "end", tags=(tag,),
                      values=(p["id"], p["name"], p["barcode"],
                              p["stock"], f"${p['price']:.2f}", f"${value:.2f}"))

        # Summary footer
        sep = tk.Frame(win, bg=BORDER, height=1)
        sep.pack(fill="x", padx=12)
        summary = tk.Frame(win, bg=BG)
        summary.pack(fill="x", padx=12, pady=6)
        tk.Label(summary, text=f"Total products: {len(PRODUCTS)}",
                 bg=BG, font=("Helvetica", 10)).pack(side="left", padx=8)
        tk.Label(summary, text=f"Total units in stock: {total_items}",
                 bg=BG, font=("Helvetica", 10)).pack(side="left", padx=8)
        tk.Label(summary, text=f"Total stock value: ${total_value:.2f}",
                 bg=BG, font=("Helvetica", 10, "bold")).pack(side="right", padx=8)

        # Buttons
        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=8)
        styled_button(btn_row, "Print",
                      lambda: messagebox.showinfo("Print",
                          "[PROTOTYPE]\nSending stock report to printer…",
                          parent=win),
                      bg=BTN_OK).pack(side="left", padx=6)
        styled_button(btn_row, "Close", win.destroy, bg=BTN_DNG).pack(side="left", padx=6)



# ── POS / New Order View ──────────────────────────────────────────────────────
class POSView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._order = []   # list of {"product": ..., "qty": int}
        self._build()

    def _build(self):
        # ── top input bar ──────────────────────────────────────────────────
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)

        tk.Label(top, text="Barcode:", bg=BG, font=("Helvetica", 10)).pack(side="left")
        self._bc_var = tk.StringVar(master=self)
        bc_entry = tk.Entry(top, textvariable=self._bc_var, width=22,
                            font=("Helvetica", 11), relief="solid", bd=1)
        bc_entry.pack(side="left", padx=6)
        bc_entry.bind("<Return>", lambda e: self._add_by_barcode())
        bc_entry.focus_set()
        styled_button(top, "Add", self._add_by_barcode, bg=BTN_OK).pack(side="left", padx=4)

        tk.Label(top, text="  or  ", bg=BG).pack(side="left")
        self._name_var = tk.StringVar(master=self)
        self._name_cb = ttk.Combobox(top, textvariable=self._name_var,
                                     values=[p["name"] for p in PRODUCTS],
                                     width=22, state="normal")
        self._name_cb.pack(side="left", padx=4)
        self._name_cb.bind("<KeyRelease>", self._on_name_key)
        self._name_cb.bind("<<ComboboxSelected>>", lambda e: self._add_by_name())
        self._name_cb.bind("<Return>", lambda e: self._add_by_name())
        styled_button(top, "Add by Name", self._add_by_name).pack(side="left", padx=4)

        self._err_lbl = tk.Label(top, text="", fg=BTN_DNG, bg=BG, font=("Helvetica", 10))
        self._err_lbl.pack(side="left", padx=8)

        # ── main split ────────────────────────────────────────────────────
        split = tk.Frame(self, bg=BG)
        split.pack(fill="both", expand=True, padx=12, pady=4)

        # Order table (left)
        left = tk.Frame(split, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        cols   = ("Product", "Qty", "Price", "Actions")
        widths = (220, 60, 90, 110)
        tv_frame, self._tv = make_treeview(left, cols, widths, height=14)
        tv_frame.pack(fill="both", expand=True)
        self._tv.bind("<ButtonRelease-1>", self._on_tv_click)

        # Summary panel (right)
        right = tk.Frame(split, bg="white", bd=1, relief="solid", width=220)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        tk.Label(right, text="ORDER SUMMARY", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 11, "bold"), pady=8).pack(fill="x")

        inner = tk.Frame(right, bg="white")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        def summary_row(label):
            f = tk.Frame(inner, bg="white")
            f.pack(fill="x", pady=3)
            tk.Label(f, text=label, bg="white", font=("Helvetica", 10),
                     anchor="w").pack(side="left")
            var = tk.StringVar(master=self, value="—")
            tk.Label(f, textvariable=var, bg="white",
                     font=("Helvetica", 10, "bold"), anchor="e").pack(side="right")
            return var

        self._items_var    = summary_row("Items:")
        self._subtotal_var = summary_row("Subtotal:")
        self._tax_var      = summary_row("Tax (0%):")
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=6)
        self._total_var    = summary_row("TOTAL:")

        styled_button(right, "Clear Order",
                      self._clear_order, bg=BTN_DNG).pack(fill="x", padx=12, pady=4)
        styled_button(right, "Checkout",
                      self._checkout, bg=BTN_OK).pack(fill="x", padx=12, pady=4)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _set_error(self, msg):
        self._err_lbl.config(text=msg)
        self.after(3000, lambda: self._err_lbl.config(text=""))

    def _add_product(self, product):
        if product["stock"] <= 0:
            self._set_error(f"'{product['name']}' is out of stock.")
            return
        for item in self._order:
            if item["product"]["id"] == product["id"]:
                item["qty"] += 1
                self._refresh_tv()
                return
        self._order.append({"product": product, "qty": 1})
        self._refresh_tv()

    def _add_by_barcode(self):
        bc = self._bc_var.get().strip()
        if not bc:
            return
        p = next((p for p in PRODUCTS if p["barcode"] == bc), None)
        if not p:
            self._set_error(f"Barcode '{bc}' not found.")
        else:
            self._add_product(p)
        self._bc_var.set("")

    def _on_name_key(self, event):
        if event.keysym in ("Return", "Up", "Down", "Escape"):
            return
        q = self._name_var.get().strip().lower()
        filtered = [p["name"] for p in PRODUCTS if not q or q in p["name"].lower()]
        self._name_cb["values"] = filtered
        if filtered and q:
            self._name_cb.event_generate("<Down>")

    def _add_by_name(self):
        query = self._name_var.get().strip()
        if not query:
            return
        p = (next((p for p in PRODUCTS if p["name"] == query), None)
             or next((p for p in PRODUCTS if p["name"].lower() == query.lower()), None)
             or next((p for p in PRODUCTS if query.lower() in p["name"].lower()), None))
        if p:
            self._add_product(p)
        else:
            self._set_error(f"No product matching '{query}'.")
        self._name_var.set("")
        self._name_cb["values"] = [p["name"] for p in PRODUCTS]

    def _refresh_tv(self):
        self._tv.delete(*self._tv.get_children())
        for i, item in enumerate(self._order):
            p   = item["product"]
            qty = item["qty"]
            tag = "alt" if i % 2 else ""
            self._tv.insert("", "end",
                            values=(p["name"], qty,
                                    f"${p['price'] * qty:.2f}",
                                    "[+]  [-]  [×]"),
                            iid=str(i), tags=(tag,))
        self._update_summary()

    def _on_tv_click(self, event):
        region = self._tv.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self._tv.identify_column(event.x)
        row = self._tv.identify_row(event.y)
        if not row or col != "#4":
            return
        idx = int(row)
        x_in_cell = event.x - self._tv.bbox(row, "#4")[0]
        cell_w = self._tv.column("#4", option="width")
        third  = cell_w / 3
        if x_in_cell < third:
            self._order[idx]["qty"] += 1
        elif x_in_cell < 2 * third:
            if self._order[idx]["qty"] > 1:
                self._order[idx]["qty"] -= 1
        else:
            self._order.pop(idx)
        self._refresh_tv()

    def _update_summary(self):
        count    = sum(i["qty"] for i in self._order)
        subtotal = sum(i["product"]["price"] * i["qty"] for i in self._order)
        self._items_var.set(str(count))
        self._subtotal_var.set(f"${subtotal:.2f}")
        self._tax_var.set("$0.00")
        self._total_var.set(f"${subtotal:.2f}")

    def _clear_order(self):
        if self._order and messagebox.askyesno("Clear Order", "Clear all items?"):
            self._order.clear()
            self._refresh_tv()

    def _checkout(self):
        global _next_order_id
        if not self._order:
            messagebox.showwarning("Empty Order", "Add at least one item before checkout.")
            return
        total = sum(i["product"]["price"] * i["qty"] for i in self._order)
        items_snapshot = [
            {"name": i["product"]["name"], "qty": i["qty"],
             "unit_price": i["product"]["price"]}
            for i in self._order
        ]
        # decrement stock
        for item in self._order:
            item["product"]["stock"] -= item["qty"]
        order_id = _next_order_id
        _next_order_id += 1
        ORDERS.insert(0, {
            "id": order_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total": total,
            "items": items_snapshot,
        })
        self._order.clear()
        self._refresh_tv()
        messagebox.showinfo("Checkout Complete",
                            f"Order #{order_id} saved.\nTotal: ${total:.2f}\n\nThank you!")


# ── Order History View ─────────────────────────────────────────────────────────
class HistoryView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)
        tk.Label(top, text="Date From:", bg=BG, font=("Helvetica", 10)).pack(side="left")
        self._from_var = tk.StringVar(master=self)
        tk.Entry(top, textvariable=self._from_var, width=12,
                 font=("Helvetica", 10), relief="solid", bd=1).pack(side="left", padx=4)
        tk.Label(top, text="To:", bg=BG, font=("Helvetica", 10)).pack(side="left", padx=(8, 0))
        self._to_var = tk.StringVar(master=self)
        tk.Entry(top, textvariable=self._to_var, width=12,
                 font=("Helvetica", 10), relief="solid", bd=1).pack(side="left", padx=4)
        styled_button(top, "Filter", self.refresh).pack(side="left", padx=8)
        styled_button(top, "Clear", self._clear_filter).pack(side="left", padx=2)

        cols   = ("ID", "Date / Time", "Items", "Total")
        widths = (60, 200, 80, 120)
        tv_frame, self._tv = make_treeview(self, cols, widths)
        tv_frame.pack(fill="both", expand=True, padx=12, pady=4)

        # Pagination
        self._pager = Pager(self, self.refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))
        self._tv.bind("<Double-1>", lambda e: self._view_details())

        bot = tk.Frame(self, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        styled_button(bot, "View Details", self._view_details).pack(side="left", padx=4)

    def refresh(self, *_):
        f = self._from_var.get().strip()
        t = self._to_var.get().strip()
        rows = []
        for o in ORDERS:
            date = o["created_at"][:10]
            if f and date < f:
                continue
            if t and date > t:
                continue
            rows.append((o["id"], o["created_at"],
                         sum(i["qty"] for i in o["items"]),
                         f"${o['total']:.2f}"))
        self._pager.set_total(len(rows))
        insert_rows(self._tv, self._pager.slice(rows))

    def _clear_filter(self):
        self._from_var.set("")
        self._to_var.set("")
        self._pager.reset()
        self.refresh()

    def _view_details(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showwarning("Selection", "Please select an order first.")
            return
        oid = int(self._tv.item(sel[0])["values"][0])
        order = next((o for o in ORDERS if o["id"] == oid), None)
        if not order:
            return

        win = tk.Toplevel(self)
        win.title(f"Order #{oid} — Details")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=f"Order #{oid}", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 12, "bold"), pady=8).pack(fill="x")
        tk.Label(win, text=f"Date: {order['created_at']}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w", padx=12, pady=(8, 2))

        cols   = ("Product", "Qty", "Unit Price", "Line Total")
        widths = (200, 60, 100, 100)
        tv_frame, tv = make_treeview(win, cols, widths, height=8)
        tv_frame.pack(padx=12, pady=8)

        for i, item in enumerate(order["items"]):
            tag = "alt" if i % 2 else ""
            line = item["qty"] * item["unit_price"]
            tv.insert("", "end", tags=(tag,),
                      values=(item["name"], item["qty"],
                              f"${item['unit_price']:.2f}", f"${line:.2f}"))

        tk.Label(win, text=f"TOTAL:  ${order['total']:.2f}",
                 bg=BG, font=("Helvetica", 11, "bold"), anchor="e").pack(
                     fill="x", padx=12, pady=(0, 4))
        styled_button(win, "Close", win.destroy, bg=BTN_DNG).pack(pady=8)


# ── Root Application Window ───────────────────────────────────────────────────
class App(tk.Tk):
    TABS = [
        ("Stock Management", StockView),
        ("POS / New Order",  POSView),
        ("Order History",    HistoryView),
    ]

    def __init__(self):
        super().__init__()
        self.title("POS Application")
        self.geometry("1024x768")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._views = {}
        self._active = None
        self._build_nav()
        self._build_content()
        self.switch_tab(0)

    def _build_nav(self):
        nav = tk.Frame(self, bg=NAV_BG, height=92)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Label(nav, text="  APA@POS",
                 bg=NAV_BG, fg=NAV_FG,
                 font=("Helvetica", 13, "bold")).pack(side="left", padx=8)

        self._tab_btns = []
        for i, (label, _) in enumerate(self.TABS):
            btn = tk.Button(nav, text=label,
                            bg=NAV_BG, fg="#1C1C1C",
                            font=("Helvetica", 10), relief="flat",
                            padx=14, pady=10, cursor="hand2",
                            command=lambda idx=i: self.switch_tab(idx))
            btn.pack(side="left")
            self._tab_btns.append(btn)

        # Store logo (right side)
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
        if os.path.exists(logo_path):
            self._logo_img = tk.PhotoImage(file=logo_path)
            tk.Label(nav, image=self._logo_img, bg=NAV_BG).pack(side="right", padx=16)
        else:
            logo = tk.Canvas(nav, bg=NAV_BG, width=64, height=64, highlightthickness=0)
            logo.pack(side="right", padx=16)
            logo.create_oval(2, 2, 62, 62, fill=NAV_ACT, outline="")
            logo.create_text(32, 32, text="APA", fill="white", font=("Helvetica", 16, "bold"))

    def _build_content(self):
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True)
        for _, ViewClass in self.TABS:
            v = ViewClass(self._content)
            self._views[ViewClass] = v

    def switch_tab(self, idx):
        _, ViewClass = self.TABS[idx]
        # hide current
        if self._active is not None:
            self._active.pack_forget()
        # highlight button
        for i, btn in enumerate(self._tab_btns):
            btn.config(bg=NAV_ACT if i == idx else NAV_BG, fg="#1C1C1C")
        # show new
        view = self._views[ViewClass]
        # refresh live data
        if hasattr(view, "refresh"):
            view.refresh()
        view.pack(fill="both", expand=True)
        self._active = view


if __name__ == "__main__":
    app = App()
    app.mainloop()
