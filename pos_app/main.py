"""APA@POS — entry point."""
import os
import sys
import traceback

# Ensure pos_app/ is on the path so all modules resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tell Windows to use the real physical DPI so Tkinter sizes match the screen.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _fatal(msg: str) -> None:
    """Show a startup error and exit. Works before Tk is initialised."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("APA@POS — Startup Error", msg)
        root.destroy()
    except Exception:
        print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    # ── DB init ───────────────────────────────────────────────────────────────
    try:
        from db.database import get_connection, close
        get_connection()
    except Exception as exc:
        _fatal(f"Database initialisation failed:\n\n{exc}")
        return

    # ── Launch UI ─────────────────────────────────────────────────────────────
    try:
        from ui.app import App
        app = App()
        app.mainloop()
    except Exception as exc:
        _fatal(f"Unexpected error:\n\n{traceback.format_exc()}")
    finally:
        try:
            close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
