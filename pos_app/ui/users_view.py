"""Users management page."""
import tkinter as tk
from tkinter import messagebox

from models import user as user_model
from ui.theme import BG, BTN_OK, BTN_DNG, FG_MUTED, HEADER_BG, HEADER_FG, styled_button


class UsersView(tk.Frame):
    PIN_PROTECTED = True

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._users: list[dict] = []
        self._build()

    def on_show(self):
        self._refresh()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(expand=True, anchor="n", fill="x", padx=60, pady=30)

        tk.Label(outer, text="Users", bg=BG,
                 font=("Helvetica", 15, "bold")).pack(anchor="w")
        tk.Label(outer, text="Names available in the checkout \"Processed by\" prompt",
                 bg=BG, font=("Helvetica", 9), fg=FG_MUTED).pack(anchor="w", pady=(2, 16))

        # Add user row
        add_row = tk.Frame(outer, bg=BG)
        add_row.pack(anchor="w", fill="x")

        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(add_row, textvariable=self._name_var, width=28,
                                    font=("Helvetica", 11), relief="solid", bd=1)
        self._name_entry.pack(side="left", padx=(0, 8), ipady=3)
        self._name_entry.bind("<Return>", lambda e: self._add_user())
        styled_button(add_row, "Add User", self._add_user, bg=BTN_OK).pack(side="left")

        # User list
        list_frame = tk.Frame(outer, bg=BG)
        list_frame.pack(fill="x", pady=(16, 0))

        # Header
        hdr = tk.Frame(list_frame, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Name", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 10, "bold"),
                 anchor="w", padx=10, pady=6).pack(side="left", fill="x", expand=True)
        tk.Label(hdr, text="Action", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Helvetica", 10, "bold"),
                 anchor="center", padx=10, width=10).pack(side="right")

        self._rows_frame = tk.Frame(list_frame, bg=BG, bd=1, relief="solid")
        self._rows_frame.pack(fill="x")

        self._empty_lbl = tk.Label(self._rows_frame,
                                    text="No users yet. Add one above.",
                                    bg=BG, fg=FG_MUTED, font=("Helvetica", 10),
                                    pady=14)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        for w in self._rows_frame.winfo_children():
            w.destroy()

        self._users = user_model.get_all()

        if not self._users:
            self._empty_lbl = tk.Label(self._rows_frame,
                                        text="No users yet. Add one above.",
                                        bg=BG, fg=FG_MUTED, font=("Helvetica", 10),
                                        pady=14)
            self._empty_lbl.pack()
            return

        for i, u in enumerate(self._users):
            bg = "#F5F5F5" if i % 2 else "white"
            row = tk.Frame(self._rows_frame, bg=bg)
            row.pack(fill="x")

            tk.Label(row, text=u["name"], bg=bg,
                     font=("Helvetica", 11), anchor="w",
                     padx=10, pady=8).pack(side="left", fill="x", expand=True)

            styled_button(row, "Remove",
                          lambda uid=u["id"]: self._remove_user(uid),
                          bg=BTN_DNG).pack(side="right", padx=8, pady=4)

    def _add_user(self):
        name = self._name_var.get().strip()
        if not name:
            return
        try:
            user_model.create(name)
            self._name_var.set("")
            self._name_entry.focus_set()
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _remove_user(self, user_id: int):
        user_model.delete(user_id)
        self._refresh()
