"""POS / New Order screen — barcode scan, autocomplete name, live order, checkout."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import product as product_model
from models import order as order_model
from models import user as user_model
from services import receipt_service
from ui.theme import (
    BG, TROW_ALT, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    styled_button, AutocompleteEntry,
)


class POSView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._order: list[dict] = []    # [{"product": dict, "qty": int}]
        self._last_processed_by: str | None = user_model.get_last_used()
        self._build()

    # ── Public hook called by App.switch_tab ──────────────────────────────────
    def on_show(self):
        self._reload_name_values()
        self._bc_entry.focus_set()

    def on_hide(self):
        self._name_ac._hide()
        self._name_ac.set("")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── input bar ─────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)

        tk.Label(top, text="Barcode:", bg=BG,
                 font=("Helvetica", 10)).pack(side="left")
        self._bc_var = tk.StringVar(master=self)
        self._bc_entry = tk.Entry(top, textvariable=self._bc_var, width=22,
                                  font=("Helvetica", 11), relief="solid", bd=1)
        self._bc_entry.pack(side="left", padx=6)
        self._bc_entry.bind("<Return>", lambda e: self._add_by_barcode())
        styled_button(top, "Add", self._add_by_barcode,
                      bg=BTN_OK).pack(side="left", padx=4)

        tk.Label(top, text="  or  ", bg=BG).pack(side="left")
        self._name_ac = AutocompleteEntry(
            top, width=26,
            on_select=self._on_name_selected,
        )
        self._name_ac.pack(side="left", padx=4)
        self._name_ac.bind("<Return>", lambda e: self._add_by_name())
        styled_button(top, "Add by Name",
                      self._add_by_name).pack(side="left", padx=4)


        # ── main split ────────────────────────────────────────────────────────
        split = tk.Frame(self, bg=BG)
        split.pack(fill="both", expand=True, padx=12, pady=4)

        # order table — left
        left = tk.Frame(split, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        # Column pixel widths (shared by header + every data row)
        _UP, _QTY, _TOT, _REM = 90, 90, 90, 40
        SEP_C = "#1A2940"   # vertical separator colour

        def col_sep(parent):
            tk.Frame(parent, bg=SEP_C, width=1).pack(side="left", fill="y")

        def fixed_cell(parent, width, bg):
            f = tk.Frame(parent, bg=bg, width=width)
            f.pack_propagate(False)
            f.pack(side="left", fill="y")
            return f

        # ── Header + canvas in a shared grid so widths match exactly ──────────
        table = tk.Frame(left, bg=BG)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(1, weight=1)

        # Header row (grid row 0, column 0)
        hdr = tk.Frame(table, bg=HEADER_BG, bd=1, relief="solid")
        hdr.grid(row=0, column=0, sticky="ew")

        # Product header — direct label, sets the header height
        tk.Label(hdr, text="Product", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 10, "bold"), pady=5,
                 anchor="w", padx=6).pack(side="left", fill="x", expand=True)

        for text, width, anchor in (
            ("Price", _UP,  "e"),
            ("Qty",        _QTY, "center"),
            ("Total",      _TOT, "e"),
            ("",           _REM, "center"),
        ):
            f = fixed_cell(hdr, width, HEADER_BG)
            tk.Label(f, text=text, bg=HEADER_BG, fg=HEADER_FG,
                     font=("Helvetica", 10, "bold"),
                     anchor=anchor).pack(fill="both", expand=True, padx=4)

        # Canvas + scrollbar (grid row 1)
        canvas = tk.Canvas(table, bg=BG, highlightthickness=0, bd=1, relief="solid")
        canvas.grid(row=1, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(table, orient="vertical", command=canvas.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        self._order_frame = tk.Frame(canvas, bg=BG)
        self._canvas_win  = canvas.create_window((0, 0), window=self._order_frame, anchor="nw")
        self._order_frame.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._canvas_win, width=e.width))

        # Store column widths for use in _refresh_tv
        self._col = (_UP, _QTY, _TOT, _REM)
        self._col_sep = col_sep
        self._fixed_cell = fixed_cell

        # summary panel — right
        right = tk.Frame(split, bg="white", bd=1, relief="solid", width=345)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        tk.Label(right, text="ORDER SUMMARY",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 11, "bold"), pady=8).pack(fill="x")

        inner = tk.Frame(right, bg="white")
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        def summary_row(label: str) -> tk.StringVar:
            f = tk.Frame(inner, bg="white")
            f.pack(fill="x", pady=3)
            tk.Label(f, text=label, bg="white",
                     font=("Helvetica", 10), anchor="w").pack(side="left")
            var = tk.StringVar(master=self, value="—")
            tk.Label(f, textvariable=var, bg="white",
                     font=("Helvetica", 10, "bold"), anchor="e").pack(side="right")
            return var

        self._items_var    = summary_row("Items:")
        self._subtotal_var = summary_row("Subtotal:")

        # Discount row
        disc_f = tk.Frame(inner, bg="white")
        disc_f.pack(fill="x", pady=3)
        tk.Label(disc_f, text="Discount:", bg="white",
                 font=("Helvetica", 10), anchor="w").pack(side="left")
        self._discount_amt_var = tk.StringVar(master=self, value="")
        tk.Label(disc_f, textvariable=self._discount_amt_var, bg="white",
                 font=("Helvetica", 10, "bold"), fg="#C0392B").pack(side="right")
        tk.Label(disc_f, text="%", bg="white",
                 font=("Helvetica", 10)).pack(side="right", padx=(0, 2))
        self._discount_var = tk.StringVar(master=self)
        self._discount_var.trace_add("write", lambda *_: self._update_summary())
        tk.Entry(disc_f, textvariable=self._discount_var, width=4,
                 font=("Helvetica", 10), relief="solid", bd=1,
                 justify="right").pack(side="right", padx=(4, 2))

        tax_pct = f"{config.TAX_RATE * 100:.4g}%"
        self._tax_var      = summary_row(f"Tax ({tax_pct}):")
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=6)
        self._total_var    = summary_row("TOTAL:")

        styled_button(right, "Clear Order",
                      self._clear_order, bg=BTN_DNG).pack(fill="x", padx=12, pady=(16, 4))
        styled_button(right, "Checkout",
                      self._checkout,    bg=BTN_OK ).pack(fill="x", padx=12, pady=4)

    # ── Name autocomplete helpers ─────────────────────────────────────────────
    def _reload_name_values(self):
        sym = config.CURRENCY_SYMBOL
        display_map = {}
        for p in product_model.get_all():
            title   = (p["title"] or "")
            author  = (p.get("author") or "")
            price   = f"{sym}{p['price']:.2f}"
            pid     = str(p["id"]).rjust(6)
            t_col   = (title[:47] + "...").ljust(50) if len(title)  > 50 else title.ljust(50)
            a_col   = (author[:47] + "...").ljust(50) if len(author) > 50 else author.ljust(50)
            stock   = str(p.get("stock", 0)).rjust(5)
            display = f"{pid}  {t_col}  {a_col}  {price}  {stock}"
            display_map[display] = title
        self._name_ac.set_display_values(display_map)

    def _on_name_selected(self, value: str) -> None:
        """Called immediately when the user picks a suggestion from the list."""
        self._add_by_name()

    # ── Add product helpers ───────────────────────────────────────────────────
    def _add_by_barcode(self):
        bc = self._bc_var.get().strip()
        if not bc:
            return
        p = product_model.get_by_barcode(bc)
        if not p:
            messagebox.showwarning("Not Found", f"Barcode '{bc}' not found.")
        else:
            self._add_product(p)
        self._bc_var.set("")
        self._bc_entry.focus_set()

    def _add_by_name(self):
        query = self._name_ac.get().strip()
        if not query:
            return
        all_products = product_model.get_all()
        p = (
            next((x for x in all_products if x["title"] == query),               None) or
            next((x for x in all_products if x["title"].lower() == query.lower()), None) or
            next((x for x in all_products if query.lower() in x["title"].lower()), None)
        )
        if p:
            self._add_product(p)
        else:
            messagebox.showwarning("Not Found", f"No product matching '{query}'.")
        self._name_ac.set("")
        self._reload_name_values()
        self._bc_entry.focus_set()

    def _add_product(self, product: dict):
        # Re-fetch from DB to get the current live stock value
        fresh = product_model.get_by_id(product["id"])
        if fresh is None:
            messagebox.showwarning("Not Found", "Product no longer exists.")
            return

        in_cart = next(
            (item["qty"] for item in self._order
             if item["product"]["id"] == fresh["id"]),
            0,
        )
        if fresh["stock"] - in_cart <= 0:
            messagebox.showwarning("Out of Stock", f"'{fresh['title']}' — insufficient stock.")
            return

        for item in self._order:
            if item["product"]["id"] == fresh["id"]:
                item["qty"] += 1
                self._refresh_tv()
                return

        self._order.append({"product": fresh, "qty": 1})
        self._refresh_tv()

    # ── Order rows ────────────────────────────────────────────────────────────
    def _refresh_tv(self):
        for w in self._order_frame.winfo_children():
            w.destroy()
        sym  = config.CURRENCY_SYMBOL
        _UP, _QTY, _TOT, _REM = self._col
        sep  = self._col_sep
        cell = self._fixed_cell

        for i, item in enumerate(self._order):
            p     = item["product"]
            qty   = item["qty"]
            bg    = TROW_ALT if i % 2 else "white"
            price = p["price"] * qty

            row = tk.Frame(self._order_frame, bg=bg)
            row.pack(fill="x")

            # Product (flexible — drives row height)
            tk.Label(row, text=p["title"], bg=bg,
                     font=("Helvetica", 10), anchor="w",
                     padx=6, pady=5).pack(side="left", fill="x", expand=True)

            # Unit Price
            f = cell(row, _UP, bg)
            tk.Label(f, text=f"{sym}{p['price']:.2f}", bg=bg,
                     font=("Helvetica", 10), anchor="e",
                     padx=4).pack(fill="both", expand=True)

            # Qty: [−] qty [+] — three equal fixed-width sub-cells
            f = cell(row, _QTY, bg)
            btn_w = _QTY // 3

            def sub(parent, w, bg=bg):
                sf = tk.Frame(parent, bg=bg, width=w)
                sf.pack_propagate(False)
                sf.pack(side="left", fill="y")
                return sf

            s = sub(f, btn_w)
            tk.Button(s, text="−", relief="flat", bg=bg,
                      font=("Helvetica", 10), cursor="hand2",
                      command=lambda idx=i: self._decrement(idx)
                      ).pack(fill="both", expand=True)
            s = sub(f, _QTY - 2 * btn_w)   # middle gets any rounding remainder
            tk.Label(s, text=str(qty), bg=bg,
                     font=("Helvetica", 10, "bold"), anchor="center"
                     ).pack(fill="both", expand=True)
            s = sub(f, btn_w)
            tk.Button(s, text="+", relief="flat", bg=bg,
                      font=("Helvetica", 10), cursor="hand2",
                      command=lambda idx=i: self._increment(idx)
                      ).pack(fill="both", expand=True)

            # Total
            f = cell(row, _TOT, bg)
            tk.Label(f, text=f"{sym}{price:.2f}", bg=bg,
                     font=("Helvetica", 10), anchor="e",
                     padx=4).pack(fill="both", expand=True)

            # Remove
            f = cell(row, _REM, bg)
            tk.Button(f, text="×", relief="flat", bg=bg,
                      fg="#E74C3C", font=("Helvetica", 11, "bold"),
                      cursor="hand2",
                      command=lambda idx=i: self._remove(idx)
                      ).pack(fill="both", expand=True)

        self._update_summary()

    def _increment(self, idx: int):
        self._order[idx]["qty"] += 1
        self._refresh_tv()

    def _decrement(self, idx: int):
        if self._order[idx]["qty"] > 1:
            self._order[idx]["qty"] -= 1
        else:
            self._order.pop(idx)
        self._refresh_tv()

    def _remove(self, idx: int):
        self._order.pop(idx)
        self._refresh_tv()


        self._refresh_tv()

    # ── Summary ───────────────────────────────────────────────────────────────
    def _update_summary(self):
        sym      = config.CURRENCY_SYMBOL
        count    = sum(i["qty"] for i in self._order)
        subtotal = sum(i["product"]["price"] * i["qty"] for i in self._order)

        try:
            disc_pct = max(0.0, min(100.0, float(self._discount_var.get() or 0)))
        except ValueError:
            disc_pct = 0.0

        disc_amt  = round(subtotal * disc_pct / 100, 2)
        discounted = subtotal - disc_amt
        tax        = round(discounted * config.TAX_RATE, 2)
        total      = discounted + tax

        self._items_var.set(str(count) if count else "—")
        self._subtotal_var.set(f"{sym}{subtotal:.2f}" if count else "—")
        self._discount_amt_var.set(f"-{sym}{disc_amt:.2f}" if (count and disc_amt) else "")
        self._tax_var.set(f"{sym}{tax:.2f}"           if count else "—")
        self._total_var.set(f"{sym}{total:.2f}"       if count else "—")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _clear_order(self):
        if not self._order:
            return
        if messagebox.askyesno("Clear Order", "Remove all items from the order?"):
            self._order.clear()
            self._refresh_tv()

    def _checkout_dialog(self) -> dict | None:
        """Unified checkout modal. Returns dict or None if cancelled."""
        users = user_model.get_all()
        result = [None]

        dlg = tk.Toplevel(self, bg=BG)
        dlg.title("Complete Order")
        dlg.resizable(False, False)
        dlg.grab_set()

        pad = {"padx": 24}

        # Processed by (only if users exist)
        user_var = tk.StringVar()
        if users:
            tk.Label(dlg, text="Processed by:", bg=BG,
                     font=("Helvetica", 10)).pack(anchor="w", pady=(20, 2), **pad)
            names   = [u["name"] for u in users]
            default = self._last_processed_by if self._last_processed_by in names else names[0]
            user_var.set(default)
            ttk.Combobox(dlg, textvariable=user_var, values=names,
                         state="readonly", font=("Helvetica", 11),
                         width=26).pack(anchor="w", **pad)

        # Payment method
        tk.Label(dlg, text="Payment method:", bg=BG,
                 font=("Helvetica", 10)).pack(anchor="w", pady=(16, 6), **pad)

        method_var = tk.StringVar(value="cash")
        methods = [("Cash", "cash"), ("Card", "card"),
                   ("Check", "check"), ("Gift", "gift")]

        btn_frame = tk.Frame(dlg, bg=BG)
        btn_frame.pack(anchor="w", **pad)
        method_btns: dict[str, tk.Button] = {}

        # Container always occupies its position; name_frame toggled inside it
        name_container = tk.Frame(dlg, bg=BG)
        name_container.pack(anchor="w", fill="x", **pad)
        name_frame = tk.Frame(name_container, bg=BG)
        tk.Label(name_frame, text="Customer name:", bg=BG,
                 font=("Helvetica", 10)).pack(anchor="w", pady=(12, 2))
        customer_var = tk.StringVar()
        tk.Entry(name_frame, textvariable=customer_var, width=28,
                 font=("Helvetica", 11), relief="solid", bd=1).pack(anchor="w")

        def _select_method(m: str):
            method_var.set(m)
            for k, b in method_btns.items():
                b.config(bg="#2E6DA4" if k == m else "#D0D0D0",
                         fg="white"   if k == m else "#1C1C1C")
            if m == "check":
                name_frame.pack(anchor="w")
            else:
                name_frame.pack_forget()

        for label, val in methods:
            b = tk.Button(btn_frame, text=label, width=7,
                          font=("Helvetica", 10), relief="flat", cursor="hand2",
                          bg="#D0D0D0", fg="#1C1C1C",
                          command=lambda v=val: _select_method(v))
            b.pack(side="left", padx=(0, 6))
            method_btns[val] = b
        _select_method("cash")

        # Buttons
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=(20, 16), **pad)

        def _confirm():
            if method_var.get() == "check" and not customer_var.get().strip():
                messagebox.showwarning("Required", "Please enter the customer name for check payment.", parent=dlg)
                return
            pb = user_var.get() or None
            if pb:
                self._last_processed_by = pb
                user_model.set_last_used(pb)
            result[0] = {
                "processed_by":   pb,
                "payment_method": method_var.get(),
                "customer_name":  customer_var.get().strip() or None,
            }
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        styled_button(btn_row, "Cancel",         _cancel).pack(side="left", padx=(0, 8))
        styled_button(btn_row, "Complete Order", _confirm, bg=BTN_OK).pack(side="left")

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width()  - dlg.winfo_width())  // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")
        self.wait_window(dlg)
        return result[0]

    def _checkout(self):
        if not self._order:
            messagebox.showwarning("Empty Order",
                                   "Add at least one item before checkout.")
            return

        checkout = self._checkout_dialog()
        if checkout is None:
            return

        try:
            disc_pct = max(0.0, min(100.0, float(self._discount_var.get() or 0)))
        except ValueError:
            disc_pct = 0.0

        items = [
            {
                "product_id": item["product"]["id"],
                "quantity":   item["qty"],
                "unit_price": item["product"]["price"],
            }
            for item in self._order
        ]

        try:
            new_order = order_model.create(
                items,
                processed_by=checkout["processed_by"],
                discount_pct=disc_pct,
                payment_method=checkout["payment_method"],
                customer_name=checkout["customer_name"],
            )
        except ValueError as exc:
            messagebox.showerror("Checkout Failed", str(exc))
            return

        sym      = config.CURRENCY_SYMBOL
        order_id = new_order["id"]
        total    = new_order["total"]

        self._order.clear()
        self._discount_var.set("")
        self._refresh_tv()
        self._reload_name_values()      # stock changed — refresh autocomplete

        # Dispatch receipt (non-blocking; checkout already succeeded)
        if config.RECEIPT_MODE != "none":
            try:
                receipt_items = order_model.get_items(order_id)
                receipt_service.print_receipt(new_order, receipt_items)
            except Exception as exc:
                messagebox.showwarning(
                    "Receipt Error",
                    f"Checkout saved (Order #{order_id}), but the receipt "
                    f"could not be sent:\n\n{exc}",
                )

        method = checkout["payment_method"]
        total_str = "GIFT" if method == "gift" else f"{sym}{total:.2f}"
        messagebox.showinfo(
            "All set!",
            f"All set!  {total_str} — Order #{order_id}",
        )
        self._bc_entry.focus_set()
