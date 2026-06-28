"""Order History screen — date filter, pagination, inline detail view."""
import tkinter as tk
from tkinter import messagebox, ttk

import config
from models import order as order_model
from services import receipt_service
from ui.theme import (
    BG, BTN_BG, BTN_FG, BTN_DNG, BTN_OK, BORDER, HEADER_BG, HEADER_FG, FG_MUTED,
    styled_button, make_treeview, insert_rows, Pager, fmt_dt,
)


class HistoryView(tk.Frame):
    PIN_PROTECTED = True
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._current_order = None
        self._current_items = []
        self._sort_col: str | None = None
        self._sort_asc: bool = True
        self._build()

    # ── Public hook called by App.switch_tab ──────────────────────────────────
    def on_show(self):
        self._show_list()
        self._refresh()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_list_panel()
        self._build_detail_panel()
        self._list_panel.pack(fill="both", expand=True)

    def _build_list_panel(self):
        self._list_panel = tk.Frame(self, bg=BG)

        # Filter bar
        top = tk.Frame(self._list_panel, bg=BG, pady=8)
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

        tk.Label(top, text="(MM/DD/YYYY)", bg=BG,
                 font=("Helvetica", 9), fg=FG_MUTED).pack(side="left", padx=(2, 12))

        styled_button(top, "Filter", self._on_filter).pack(side="left", padx=4)
        styled_button(top, "Clear",  self._clear_filter).pack(side="left", padx=2)

        # Table
        cols   = ("ID", "Date / Time", "Items", "Total", "By")
        widths = (65, 200, 80, 130, 120)
        tv_frame, self._tv = make_treeview(self._list_panel, cols, widths,
                                           left_cols=("Date / Time", "Total", "By"),
                                           right_cols=())
        tv_frame.pack(fill="both", expand=True, padx=12, pady=4)
        self._tv.bind("<Double-1>", lambda e: self._view_details())

        for col in cols:
            self._tv.heading(col, command=lambda c=col: self._sort_by(c))

        # Pager
        self._pager = Pager(self._list_panel, config.PAGE_SIZE, self._refresh)
        self._pager.pack(fill="x", padx=12, pady=(0, 2))

        # Action buttons
        bot = tk.Frame(self._list_panel, bg=BG, pady=8)
        bot.pack(fill="x", padx=12)
        self._btn_details = styled_button(bot, "View Details", self._view_details)
        self._btn_details.pack(side="left", padx=4)
        styled_button(bot, "Print Report", self._print_report,
                      bg=BTN_OK).pack(side="left", padx=4)
        styled_button(bot, "Detailed Report", self._print_detailed_report,
                      bg=BTN_OK).pack(side="left", padx=4)

        self._selection_btns = [(self._btn_details, BTN_BG, BTN_FG)]
        self._tv.bind("<<TreeviewSelect>>", self._on_selection)

    def _build_detail_panel(self):
        self._detail_panel = tk.Frame(self, bg=BG)

        # Header bar with Back button + order title
        hdr = tk.Frame(self._detail_panel, bg=HEADER_BG)
        hdr.pack(fill="x")

        styled_button(hdr, "← Back", self._show_list,
                      bg=BTN_BG).pack(side="left", padx=12, pady=8)
        self._detail_title = tk.Label(hdr, text="", bg=HEADER_BG, fg=HEADER_FG,
                                      font=("Helvetica", 12, "bold"))
        self._detail_title.pack(side="left", padx=8)

        # Meta info
        self._detail_meta = tk.Frame(self._detail_panel, bg=BG)
        self._detail_meta.pack(fill="x", padx=14, pady=(10, 2))

        # Footer (packed before treeview so expand=True doesn't push it off-screen)
        tk.Frame(self._detail_panel, bg=BORDER, height=1).pack(fill="x", padx=14, side="bottom")
        self._detail_foot = tk.Frame(self._detail_panel, bg=BG)
        self._detail_foot.pack(fill="x", padx=14, pady=8, side="bottom")
        self._detail_total_lbl = tk.Label(self._detail_foot, text="",
                                          bg=BG, font=("Helvetica", 11, "bold"))
        self._detail_total_lbl.pack(side="right")
        styled_button(self._detail_foot, "Print Receipt", self._reprint_receipt,
                      bg=BTN_OK).pack(side="left")

        # Items table
        cols   = ("Product", "Qty", "Unit Price", "Line Total")
        widths = (400, 80, 140, 160)
        tv_frame, self._detail_tv = make_treeview(
            self._detail_panel, cols, widths,
            left_cols=("Product", "Unit Price", "Line Total"),
            right_cols=(),
        )
        tv_frame.pack(fill="both", expand=True, padx=14, pady=8)

    # ── Panel switching ───────────────────────────────────────────────────────
    def _show_list(self):
        self._detail_panel.pack_forget()
        self._list_panel.pack(fill="both", expand=True)

    def _show_detail(self):
        self._list_panel.pack_forget()
        self._detail_panel.pack(fill="both", expand=True)

    # ── Data refresh ──────────────────────────────────────────────────────────
    def _on_filter(self):
        self._pager.reset()
        self._refresh()

    def _clear_filter(self):
        self._from_var.set("")
        self._to_var.set("")
        self._pager.reset()
        self._refresh()

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._update_headings()
        self._pager.reset()
        self._refresh()

    def _update_headings(self):
        cols = ("ID", "Date / Time", "Items", "Total", "By")
        for col in cols:
            arrow = (" ▲" if self._sort_asc else " ▼") if col == self._sort_col else ""
            self._tv.heading(col, text=col + arrow)

    _DISABLED_BG = "#BDBDBD"
    _DISABLED_FG = "#888888"

    def _on_selection(self, *_):
        has_sel = bool(self._tv.selection())
        for btn, active_bg, active_fg in self._selection_btns:
            if has_sel:
                btn.config(state="normal", bg=active_bg, fg=active_fg, cursor="hand2")
            else:
                btn.config(state="disabled", bg=self._DISABLED_BG, fg=self._DISABLED_FG, cursor="")

    @staticmethod
    def _to_iso(us_date: str) -> str | None:
        """Convert MM/DD/YYYY → YYYY-MM-DD; return None if blank or unparseable."""
        s = us_date.strip()
        if not s:
            return None
        try:
            from datetime import datetime
            return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _refresh(self, *_):
        date_from = self._to_iso(self._from_var.get())
        date_to   = self._to_iso(self._to_var.get())

        orders = order_model.get_all(date_from=date_from, date_to=date_to)

        sym  = config.CURRENCY_SYMBOL
        raw  = []
        for o in orders:
            count = order_model.item_count(o["id"])
            raw.append({
                "id":    o["id"],
                "dt":    o["created_at"],
                "count": count,
                "total": o["total"],
                "by":    o.get("processed_by") or "",
            })

        _key = {
            "ID":          lambda r: r["id"],
            "Date / Time": lambda r: r["dt"],
            "Items":       lambda r: r["count"],
            "Total":       lambda r: r["total"],
            "By":          lambda r: r["by"].lower(),
        }
        if self._sort_col and self._sort_col in _key:
            raw.sort(key=_key[self._sort_col], reverse=not self._sort_asc)

        rows = [
            (r["id"], fmt_dt(r["dt"]), r["count"],
             f"{sym}{r['total']:.2f}", r["by"] or "—")
            for r in raw
        ]

        self._pager.set_total(len(rows))
        insert_rows(self._tv, self._pager.slice(rows))
        self._on_selection()

    # ── Detail view ───────────────────────────────────────────────────────────
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
        self._current_order = order
        self._current_items = items
        if not order:
            messagebox.showerror("Error", f"Order #{oid} not found.")
            return

        # Populate header
        self._detail_title.config(text=f"Order #{oid}  —  {fmt_dt(order['created_at'])}")

        # Populate meta
        for w in self._detail_meta.winfo_children():
            w.destroy()
        total_qty = sum(i["quantity"] for i in items)
        tk.Label(self._detail_meta, text=f"Items: {total_qty}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        by = order.get("processed_by") or "—"
        tk.Label(self._detail_meta, text=f"Processed by: {by}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        method = (order.get("payment_method") or "cash").upper()
        customer = order.get("customer_name")
        method_str = f"{method}  —  {customer}" if customer else method
        tk.Label(self._detail_meta, text=f"Payment: {method_str}",
                 bg=BG, font=("Helvetica", 10)).pack(anchor="w")
        disc = order.get("discount_pct") or 0
        if disc:
            tk.Label(self._detail_meta, text=f"Discount: {disc:.4g}%",
                     bg=BG, font=("Helvetica", 10), fg="#C0392B").pack(anchor="w")

        # Populate items table
        self._detail_tv.delete(*self._detail_tv.get_children())
        sym = config.CURRENCY_SYMBOL
        for i, item in enumerate(items):
            line = item["quantity"] * item["unit_price"]
            tag  = "alt" if i % 2 else ""
            self._detail_tv.insert("", "end", tags=(tag,),
                                   values=(
                                       item["product_name"],
                                       item["quantity"],
                                       f"{sym}{item['unit_price']:.2f}",
                                       f"{sym}{line:.2f}",
                                   ))

        # Populate footer
        self._detail_total_lbl.config(
            text=f"ORDER TOTAL:  {sym}{order['total']:.2f}"
        )

        self._show_detail()

    def _print_report(self):
        date_from = self._to_iso(self._from_var.get())
        date_to   = self._to_iso(self._to_var.get())
        orders    = order_model.get_all(date_from=date_from, date_to=date_to)
        if not orders:
            messagebox.showinfo("Report", "No orders found for the selected period.")
            return
        try:
            receipt_service.build_sales_report_pdf(orders, date_from, date_to)
        except Exception as exc:
            messagebox.showwarning("Report Error", str(exc))

    def _print_detailed_report(self):
        date_from = self._to_iso(self._from_var.get())
        date_to   = self._to_iso(self._to_var.get())
        orders    = order_model.get_all(date_from=date_from, date_to=date_to)
        if not orders:
            messagebox.showinfo("Report", "No orders found for the selected period.")
            return
        try:
            receipt_service.build_detailed_report_pdf(orders, date_from, date_to)
        except Exception as exc:
            messagebox.showwarning("Report Error", str(exc))

    def _reprint_receipt(self):
        if not self._current_order:
            return
        try:
            receipt_service.print_receipt(self._current_order, self._current_items)
        except Exception as exc:
            messagebox.showwarning("Receipt Error", str(exc))
