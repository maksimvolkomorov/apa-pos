"""Shared UI constants, widget factories, and the Pager control."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk


def fmt_dt(iso: str) -> str:
    """Convert ISO datetime ('2026-06-21 14:30:00') to US display format ('06/21/2026 02:30 PM')."""
    try:
        return datetime.strptime(iso[:16], "%Y-%m-%d %H:%M").strftime("%m/%d/%Y %I:%M %p")
    except (ValueError, TypeError):
        return iso


# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#F5F5F5"
NAV_BG    = "#2C3E50"
NAV_ACT   = "#1ABC9C"
BTN_BG    = "#3498DB"
BTN_FG    = "#1C1C1C"
BTN_DNG   = "#E74C3C"
BTN_OK    = "#2ECC71"
TROW_ALT  = "#EAF4FB"
TROW_WARN = "#FDECEA"
HEADER_BG = "#2980B9"
HEADER_FG = "#FFFFFF"
BORDER    = "#BDC3C7"
FG_MUTED  = "#7F8C8D"


def _darken(hex_color: str) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r, g, b = max(0, r - 22), max(0, g - 22), max(0, b - 22)
    return f"#{r:02x}{g:02x}{b:02x}"


def styled_button(parent, text, command, bg=BTN_BG, fg=BTN_FG, **kw):
    b = tk.Button(parent, text=text, command=command,
                  bg=bg, fg=fg, relief="flat", padx=10, pady=4,
                  font=("Helvetica", 10), cursor="hand2", **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_darken(bg)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def make_treeview(parent, columns, col_widths, height=12,
                  left_cols=(), right_cols=()):
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
        if col in left_cols:
            anchor = "w"
        elif col in right_cols:
            anchor = "e"
        else:
            anchor = "center"
        tv.heading(col, text=col, anchor=anchor)
        tv.column(col, width=w, anchor=anchor)
    tv.tag_configure("alt",  background=TROW_ALT)
    tv.tag_configure("warn", background=TROW_WARN)

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=vsb.set)
    tv.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    return frame, tv


def insert_rows(tv, rows, warn_indices: set = None):
    """Populate treeview. Rows in warn_indices get the warning background."""
    warn_indices = warn_indices or set()
    tv.delete(*tv.get_children())
    for i, row in enumerate(rows):
        if i in warn_indices:
            tag = "warn"
        elif i % 2:
            tag = "alt"
        else:
            tag = ""
        tv.insert("", "end", values=row, tags=(tag,))


# ── Pager ─────────────────────────────────────────────────────────────────────
class Pager(tk.Frame):
    def __init__(self, parent, page_size: int, on_change):
        super().__init__(parent, bg=BG)
        self.page_size = page_size
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

    def set_total(self, total: int):
        self._total = total
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        self._page = min(self._page, pages)
        self._label.config(text=f"Page {self._page} of {pages}")
        self._prev_btn.config(state="normal" if self._page > 1    else "disabled")
        self._next_btn.config(state="normal" if self._page < pages else "disabled")

    def slice(self, rows: list) -> list:
        start = (self._page - 1) * self.page_size
        return rows[start : start + self.page_size]

    def _prev(self):
        if self._page > 1:
            self._page -= 1
            self._on_change()

    def _next(self):
        pages = max(1, (self._total + self.page_size - 1) // self.page_size)
        if self._page < pages:
            self._page += 1
            self._on_change()


# ── Autocomplete Entry ────────────────────────────────────────────────────────
class AutocompleteEntry(tk.Frame):
    """
    Plain text Entry with a floating suggestion list.
    Replaces ttk.Combobox so there is no dropdown-arrow button.

    Usage:
        ac = AutocompleteEntry(parent, width=24,
                               on_select=callback_receiving_value)
        ac.set_values(["Apple", "Banana", "Apricot"])
        ac.pack(...)
        value = ac.get()
        ac.set("")
    """
    _DROP_MAX = 7
    _ROW_H    = 24

    def __init__(self, parent, width: int = 24, on_select=None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._values:   list[str]           = []
        self._on_select                     = on_select
        self._drop_win: tk.Toplevel | None  = None
        self._listbox:  tk.Listbox  | None  = None
        self._after_id: str | None          = None

        self._var = tk.StringVar(master=self)
        self._entry = tk.Entry(self, textvariable=self._var, width=width,
                               font=("Helvetica", 10), relief="solid", bd=1)
        self._entry.pack(fill="x")

        self._var.trace_add("write", self._on_var_change)
        self._entry.bind("<Down>",     self._focus_list)
        self._entry.bind("<Escape>",   lambda e: self._hide())
        self._entry.bind("<Return>",   self._on_entry_return)
        self._entry.bind("<FocusOut>", self._on_entry_focus_out)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_values(self, values: list[str]) -> None:
        self._values = list(values)

    def get(self) -> str:
        return self._var.get()

    def set(self, value: str) -> None:
        self._var.set(value)

    def focus_set(self):
        self._entry.focus_set()

    def bind(self, sequence, func, add=None):
        return self._entry.bind(sequence, func, add)

    # ── Suggestion list ───────────────────────────────────────────────────────
    def _matches(self) -> list[str]:
        q = self._var.get().strip().lower()
        if not q:
            return []
        return [v for v in self._values if q in v.lower()]

    def _on_var_change(self, *_) -> None:
        matches = self._matches()
        if matches:
            self._show(matches)
        else:
            self._hide()

    def _show(self, matches: list[str]) -> None:
        n = min(len(matches), self._DROP_MAX)
        if self._drop_win is None:
            self._drop_win = tk.Toplevel(self)
            self._drop_win.wm_overrideredirect(True)
            self._drop_win.configure(bg=BORDER)
            self._listbox = tk.Listbox(
                self._drop_win,
                font=("Helvetica", 10),
                relief="flat", bd=0,
                selectbackground=NAV_ACT,
                selectforeground="#1C1C1C",
                activestyle="none",
                height=n,
            )
            self._listbox.pack(fill="both", expand=True, padx=1, pady=1)
            self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
            self._listbox.bind("<Return>",           self._on_list_return)
            self._listbox.bind("<Escape>",           lambda e: self._hide())
            self._listbox.bind("<FocusOut>",         self._on_list_focus_out)

        self._listbox.delete(0, "end")
        for m in matches:
            self._listbox.insert("end", m)
        self._listbox.config(height=n)

        self._entry.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = self._entry.winfo_width()
        h = n * self._ROW_H + 2
        self._drop_win.geometry(f"{w}x{h}+{x}+{y}")
        self._drop_win.lift()

    def _hide(self) -> None:
        if self._drop_win:
            self._drop_win.destroy()
            self._drop_win = None
            self._listbox  = None

    # ── Keyboard / focus handlers ─────────────────────────────────────────────
    def _focus_list(self, _=None) -> None:
        if self._listbox:
            self._listbox.focus_set()
            if not self._listbox.curselection():
                self._listbox.selection_set(0)
                self._listbox.activate(0)

    def _on_entry_return(self, _=None) -> None:
        matches = self._matches()
        if matches:
            self._select(matches[0])

    def _on_list_return(self, _=None) -> None:
        if self._listbox:
            sel = self._listbox.curselection()
            if sel:
                self._select(self._listbox.get(sel[0]))

    def _on_list_select(self, _=None) -> None:
        if self._listbox:
            sel = self._listbox.curselection()
            if sel:
                self._select(self._listbox.get(sel[0]))

    def _on_entry_focus_out(self, _=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(150, self._check_focus)

    def _on_list_focus_out(self, _=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(150, self._check_focus)

    def _check_focus(self) -> None:
        try:
            focused = self.focus_get()
            if focused not in (self._entry, self._listbox):
                self._hide()
        except Exception:
            self._hide()

    def _select(self, value: str) -> None:
        self._hide()
        self._var.set(value)
        if self._on_select:
            self._on_select(value)
