"""Root Tk window with top navigation bar."""
import ctypes
import ctypes.wintypes
import os
import sys
import traceback
import tkinter as tk
from tkinter import messagebox


def _work_area() -> tuple[int, int, int, int]:
    """Return (x, y, width, height) of the usable screen area excluding the taskbar."""
    if sys.platform == "win32":
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, None, None

import config
from ui.theme import NAV_BG, NAV_ACT, BG, styled_button, show_pin_lock
from ui.stock_view import StockView
from ui.pos_view import POSView
from ui.history_view import HistoryView
from ui.import_export_view import ImportExportView
from ui.users_view import UsersView


class App(tk.Tk):
    TABS = [
        ("Sale",             POSView),
        ("Inventory",        StockView),
        ("Order History",    HistoryView),
        ("Import / Export",  ImportExportView),
        ("Users",            UsersView),
    ]

    def __init__(self):
        super().__init__()
        self.title("APA@POS")
        wa_x, wa_y, avail_w, avail_h = _work_area()
        if avail_w is None:
            avail_w = self.winfo_screenwidth()
            avail_h = self.winfo_screenheight() - 60
        win_w = min(config.WINDOW_WIDTH  or avail_w, avail_w)
        win_h = min(config.WINDOW_HEIGHT or avail_h, avail_h)
        self.geometry(f"{win_w}x{win_h}+{wa_x}+{wa_y}")
        self.update_idletasks()
        # Account for title bar: winfo_rooty is the client area top in screen coords
        deco_h = self.winfo_rooty() - self.winfo_y()
        win_h  = max(100, win_h - deco_h)
        self.geometry(f"{win_w}x{win_h}+{wa_x}+{wa_y}")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._set_icon()
        self._install_exception_handler()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._views: dict[type, tk.Frame] = {}
        self._active: tk.Frame | None = None
        self._build_nav()
        self._build_content()
        self.switch_tab(0)

    # ── Window lifecycle ──────────────────────────────────────────────────────
    def _on_close(self) -> None:
        from db.database import close
        close()
        self.destroy()

    def _install_exception_handler(self) -> None:
        """Route unhandled Tkinter callback exceptions to an error dialog."""
        def handler(exc_type, exc_value, exc_tb):
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            messagebox.showerror("Unexpected Error", msg, parent=self)
        self.report_callback_exception = handler

    def _set_icon(self):
        logo_path = os.path.join(config._BUNDLED, "assets", "apa-app-logo.png")
        if os.path.exists(logo_path):
            self._icon_img = tk.PhotoImage(file=logo_path)
            self.iconphoto(True, self._icon_img)

    # ── Nav bar ───────────────────────────────────────────────────────────────
    def _build_nav(self):
        nav = tk.Frame(self, bg=NAV_BG, height=92)
        nav.pack(fill="x")
        nav.pack_propagate(False)

        tk.Label(nav, text="  APA@POS",
                 bg=NAV_BG, fg="#1C1C1C",
                 font=("Helvetica", 13, "bold")).pack(side="left", padx=8)

        self._tab_btns: list[tk.Button] = []
        for i, (label, _) in enumerate(self.TABS):
            btn = tk.Button(nav, text=label,
                            bg=NAV_BG, fg="#1C1C1C",
                            font=("Helvetica", 10), relief="flat",
                            padx=14, pady=10, cursor="hand2",
                            command=lambda idx=i: self.switch_tab(idx))
            btn.pack(side="left")
            self._tab_btns.append(btn)

        # Store logo (right side)
        logo_path = os.path.join(config._BUNDLED, "assets", "logo.png")
        if os.path.exists(logo_path):
            self._logo_img = tk.PhotoImage(file=logo_path)
            tk.Label(nav, image=self._logo_img, bg=NAV_BG).pack(side="right", padx=16)
        else:
            logo = tk.Canvas(nav, bg=NAV_BG, width=64, height=64, highlightthickness=0)
            logo.pack(side="right", padx=16)
            logo.create_oval(2, 2, 62, 62, fill=NAV_ACT, outline="")
            logo.create_text(32, 32, text="APA", fill="white",
                             font=("Helvetica", 16, "bold"))

    # ── Content area ──────────────────────────────────────────────────────────
    def _build_content(self):
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True)
        for _, ViewClass in self.TABS:
            v = ViewClass(self._content)
            self._views[ViewClass] = v

    def switch_tab(self, idx: int):
        _, ViewClass = self.TABS[idx]
        if self._active is not None:
            if hasattr(self._active, "on_hide"):
                self._active.on_hide()
            if self._active in self._views.values():
                self._active.pack_forget()
            else:
                self._active.destroy()
        self.focus_set()
        for i, btn in enumerate(self._tab_btns):
            btn.config(bg=NAV_ACT if i == idx else NAV_BG, fg="#1C1C1C")
        view = self._views[ViewClass]
        if getattr(view, "PIN_PROTECTED", False):
            pin_frame = tk.Frame(self._content, bg=BG)
            pin_frame.pack(fill="both", expand=True)
            self._active = pin_frame

            def _on_success(v=view):
                pin_frame.destroy()
                if hasattr(v, "on_show"):
                    v.on_show()
                v.pack(fill="both", expand=True)
                self._active = v

            show_pin_lock(pin_frame, on_success=_on_success)
        else:
            if hasattr(view, "on_show"):
                view.on_show()
            view.pack(fill="both", expand=True)
            self._active = view
