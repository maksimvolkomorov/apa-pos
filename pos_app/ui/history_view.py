"""Order History screen — date filter, pagination, detail modal."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import order as order_model
from ui.theme import (
    BG, BTN_DNG, BTN_BG, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    styled_button, make_treeview, insert_rows, Pager, fmt_dt,
)


class HistoryView(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()

    # ── Public hook called by App.switch_tab ──────────────────────────────────
    def on_show(self):
        self._refresh()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # Filter bar
        top = tk.Frame(self, bg=BG, pady=8)
        top.pack(fill="x", padx=12)

        tk.Label(top, text="Date From:", bg=BG,
                 font=("Helvetica", 10)).pack(side="left")
        self._from_var = tk.StringVar(master=self)
        tk.Entry(top, textvariable=self._from_var, width=12,
                 font=("Helvetica", 10), relief="solid", bd=1,
                 ).pack(side="left", padx=4)

        tk.Label(top, text="To:", bg=BG,
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 0))
        self._to_var = tk.StringVar(master=self)
        tk.Entry(top, textvariable=self._to_var, width=12,
                 font=("Helvetica", 10), relief="solid", bd=1,
                 ).pack(side="left", padx=4)

        tk.Label(top, text="(YYYY-MM-DD)", bg=BG,
                 font=("Helvetica", 9), fg=FG_MUTED).pack(side="left", padx=(2, 12))

        styled_button(top, "Filter", self._on_filter).pack(side="left", padx=4)
        styled_button(top, "Clear",  self._clear_filter).pack(side="left", padx=2)

        # Table
        cols   = ("ID", "Date / Time", "Items", "Total")
        widths = (65, 200, 80, 130)
        tv_frame, self._tv = make_treeview(self, cols, widths,
                                           left_cols=("Date / Time", "Total"),
                                           right_cols=())
        tv_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._tv.bind("<Double-1>", lambda e: self._view_details())

        # Pager
        self._pager = Pager(self, config.PAGE_SIZE, self._refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Action buttons
        bot = tk.Frame(self, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        styled_button(bot, "View Details", self._view_details).pack(side="left", padx=4)

    # ── Data refresh ──────────────────────────────────────────────────────────
    def _on_filter(self):
        self._pager.reset()
        self._refresh()

    def _clear_filter(self):
        self._from_var.set("")
        self._to_var.set("")
        self._pager.reset()
        self._refresh()

    def _refresh(self, *_):
        date_from = self._from_var.get().strip() or None
        date_to   = self._to_var.get().strip()   or None

        orders = order_model.get_all(date_from=date_from, date_to=date_to)

        sym  = config.CURRENCY_SYMBOL
        rows = []
        for o in orders:
            count = order_model.item_count(o["id"])
            rows.append((
                o["id"],
                fmt_dt(o["created_at"]),
                count,
                f"{sym}{o['total']:.2f}",
            ))

        self._pager.set_total(len(rows))
        insert_rows(self._tv, self._pager.slice(rows))

    # ── Detail modal ──────────────────────────────────────────────────────────
    def _selected_order_id(self) -> int | None:
        sel = self._tv.selection()
        if not sel:
            messagebox.showwarning("Selection", "Please select an order first.")
            return None
        return int(self._tv.item(sel[0])["values"][0])

    def _view_details(self):
        oid = self._selected_order_id()
        if oid is None:
            return

        order = order_model.get_by_id(oid)
        items = order_model.get_items(oid)
        if not order:
            messagebox.showerror("Error", f"Order #{oid} not found.")
            return

        win = tk.Toplevel(self)
        win.title(f"Order #{oid} — Details")
        win.configure(bg=BG)
        win.resizable(True, False)
        win.transient(self)
        win.grab_set()

        # Header
        tk.Label(win, text=f"Order #{oid}",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 12, "bold"), pady=8).pack(fill="x")

        meta = tk.Frame(win, bg=BG)
        meta.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(meta, text=f"Date:   {fmt_dt(order['created_at'])}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        tk.Label(meta,
                 text=f"Items:  {sum(i['quantity'] for i in items)}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w", pady=(2, 0))

        # Items table
        cols   = ("Product", "Qty", "Unit Price", "Line Total")
        widths = (210, 55, 100, 110)
        tv_frame, tv = make_treeview(win, cols, widths,
                                     height=min(len(items), 12),
                                     left_cols=("Product", "Unit Price", "Line Total"),
                                     right_cols=())
        tv_frame.pack(fill="x", padx=14, pady=8)

        sym = config.CURRENCY_SYMBOL
        for i, item in enumerate(items):
            line = item["quantity"] * item["unit_price"]
            tag  = "alt" if i % 2 else ""
            tv.insert("", "end", tags=(tag,),
                      values=(
                          item["product_name"],
                          item["quantity"],
                          f"{sym}{item['unit_price']:.2f}",
                          f"{sym}{line:.2f}",
                      ))

        # Footer
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=14)
        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=14, pady=6)
        tk.Label(foot,
                 text=f"ORDER TOTAL:  {sym}{order['total']:.2f}",
                 bg=BG, font=("Helvetica", 11, "bold")).pack(side="right")

        styled_button(win, "Close", win.destroy,
                      bg=BTN_DNG).pack(pady=(4, 12))

        # Centre over parent
        win.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width()  - win.winfo_width())  // 2
        py = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{px}+{py}")
