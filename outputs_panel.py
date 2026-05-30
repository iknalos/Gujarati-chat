"""OutputsPanel — a Tk Frame variant of the old OutputsWindow, designed to be
embedded inside the main GujaratiClaude dashboard rather than its own Toplevel.

Same thread-safe API (push_file, seed_existing) so the watcher wiring is
unchanged from when it was a separate window.
"""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import font as tkfont
from tkinter import ttk


_ICON_BY_EXT = {
    ".png": "🖼", ".jpg": "🖼", ".jpeg": "🖼", ".gif": "🖼",
    ".bmp": "🖼", ".svg": "🖼", ".webp": "🖼",
    ".xlsx": "📊", ".xls": "📊", ".csv": "📊",
    ".html": "🌐", ".htm": "🌐",
    ".pdf": "📑",
    ".txt": "📄", ".md": "📄", ".log": "📄",
    ".json": "📄", ".yaml": "📄", ".yml": "📄",
    ".py": "🐍", ".js": "📜", ".ts": "📜",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n // 1024} KB"
    return f"{n // (1024 * 1024)} MB"


class OutputsPanel(tk.Frame):
    def __init__(self, parent: tk.Widget, outputs_dir: Path) -> None:
        super().__init__(parent)
        self.outputs_dir = outputs_dir
        self._events: Queue[Path] = Queue()
        self._preview_image_ref = None  # prevent PhotoImage GC

        gu_font = tkfont.Font(family="Nirmala UI", size=10)
        mono_font = tkfont.Font(family="Consolas", size=8)

        tk.Label(
            self, text=f"📂 {outputs_dir}", font=mono_font, anchor="w",
            foreground="#666666",
        ).pack(side="top", fill="x", pady=(0, 4))

        list_frame = tk.Frame(self)
        list_frame.pack(side="top", fill="x")
        self._tree = ttk.Treeview(
            list_frame, columns=("name", "size", "time"), show="headings", height=8,
        )
        self._tree.heading("name", text="File")
        self._tree.heading("size", text="Size")
        self._tree.heading("time", text="Time")
        self._tree.column("name", width=240, stretch=True)
        self._tree.column("size", width=70, anchor="e", stretch=False)
        self._tree.column("time", width=80, stretch=False)
        self._tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_open)
        self._tree.bind("<Return>", self._on_open)

        btn_row = tk.Frame(self)
        btn_row.pack(side="top", fill="x", pady=(4, 6))
        tk.Button(btn_row, text="Open ⤴", command=self._on_open).pack(side="left")
        tk.Button(btn_row, text="Folder", command=self._open_folder).pack(side="left", padx=(4, 0))
        tk.Button(btn_row, text="Refresh", command=self._refresh_now).pack(side="right")

        self._preview = tk.Label(
            self,
            text="(કોઈ ફાઇલ પસંદ નથી)\n\nClaude saves charts & files here.",
            anchor="center", font=gu_font,
            background="#f5f5f5", borderwidth=1, relief="solid",
        )
        self._preview.pack(side="bottom", fill="both", expand=True)

        self.after(100, self._drain_events)

    # ---- Thread-safe API -------------------------------------------------

    def push_file(self, path: Path) -> None:
        self._events.put(path)

    def seed_existing(self, paths: list[Path]) -> None:
        for p in paths:
            self._events.put(p)

    # ---- Internals -------------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                path = self._events.get_nowait()
                self._insert_file(path)
        except Empty:
            pass
        self.after(500, self._drain_events)

    def _refresh_now(self) -> None:
        try:
            for p in sorted(self.outputs_dir.iterdir(), key=lambda x: x.stat().st_mtime):
                if p.is_file():
                    self._insert_file(p.resolve())
        except OSError:
            pass

    def _insert_file(self, path: Path) -> None:
        if not path.exists():
            return
        ext = path.suffix.lower()
        icon = _ICON_BY_EXT.get(ext, "📄")
        try:
            stat = path.stat()
            size = _fmt_size(stat.st_size)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M:%S")
        except OSError:
            size, mtime = "", ""
        iid = str(path)
        values = (f"{icon}  {path.name}", size, mtime)
        if self._tree.exists(iid):
            self._tree.item(iid, values=values)
            self._tree.move(iid, "", 0)
        else:
            self._tree.insert("", 0, iid=iid, values=values)
        self._tree.selection_set(iid)
        self._tree.see(iid)
        if ext in _IMAGE_EXTS:
            self._show_preview(path)
        else:
            self._show_no_preview(path)

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        if path.suffix.lower() in _IMAGE_EXTS:
            self._show_preview(path)
        else:
            self._show_no_preview(path)

    def _on_open(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        try:
            os.startfile(str(path))
        except OSError as exc:
            self._preview.configure(image="", text=f"Couldn't open: {exc}")
            self._preview_image_ref = None

    def _open_folder(self) -> None:
        try:
            os.startfile(str(self.outputs_dir))
        except OSError:
            pass

    def _show_preview(self, path: Path) -> None:
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self._preview.configure(image="", text="(Pillow not installed)")
            self._preview_image_ref = None
            return
        try:
            img = Image.open(path)
            img.thumbnail((420, 280))
            tk_img = ImageTk.PhotoImage(img)
            self._preview.configure(image=tk_img, text="")
            self._preview_image_ref = tk_img
        except Exception as exc:
            self._preview.configure(image="", text=f"Cannot preview: {exc}")
            self._preview_image_ref = None

    def _show_no_preview(self, path: Path) -> None:
        self._preview.configure(
            image="",
            text=f"{path.name}\n\n(Double-click or Open ⤴ to view)",
        )
        self._preview_image_ref = None
