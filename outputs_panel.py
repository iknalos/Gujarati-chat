"""OutputsPanel — themed Tk Frame embedded in the GujaratiClaude dashboard.

Shows the contents of outputs/ as a file list with image preview. Uses ttk
widgets so the parent's sv_ttk theme applies. The preview Label remains a
plain tk widget (for displaying PhotoImage) with dark-theme colors.
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
_HTML_EXTS  = {".html", ".htm", ".svg"}

# Dark-theme preview colors (sv_ttk dark mode).
_PREVIEW_BG = "#1e1e1e"
_PREVIEW_FG = "#9aa0a6"


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n // 1024} KB"
    return f"{n // (1024 * 1024)} MB"


class OutputsPanel(ttk.Frame):
    def __init__(self, parent: tk.Widget, outputs_dir: Path) -> None:
        super().__init__(parent)
        self.outputs_dir = outputs_dir
        self._events: Queue[Path] = Queue()
        self._preview_image_ref = None  # prevent PhotoImage GC

        gu_font = tkfont.Font(family="Nirmala UI", size=11)
        mono_font = tkfont.Font(family="Consolas", size=9)

        ttk.Label(
            self, text=f"📂 {outputs_dir}", font=mono_font, anchor="w",
        ).pack(side="top", fill="x", pady=(0, 6), padx=2)

        list_frame = ttk.Frame(self)
        list_frame.pack(side="top", fill="x")
        self._tree = ttk.Treeview(
            list_frame, columns=("name", "size", "time"), show="headings", height=9,
        )
        self._tree.heading("name", text="File")
        self._tree.heading("size", text="Size")
        self._tree.heading("time", text="Time")
        self._tree.column("name", width=260, stretch=True)
        self._tree.column("size", width=70, anchor="e", stretch=False)
        self._tree.column("time", width=80, stretch=False)
        self._tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_open)
        self._tree.bind("<Return>", self._on_open)

        btn_row = ttk.Frame(self)
        btn_row.pack(side="top", fill="x", pady=(6, 8))
        ttk.Button(btn_row, text="Open ⤴", command=self._on_open).pack(side="left")
        ttk.Button(btn_row, text="Folder", command=self._open_folder).pack(side="left", padx=(6, 0))
        ttk.Button(btn_row, text="Refresh", command=self._refresh_now).pack(side="right")

        # Preview area: a container that swaps between image Label and an
        # HtmlFrame for HTML/SVG artifacts. Both widgets are pre-built; we
        # pack/forget based on what's selected.
        self._preview_box = ttk.Frame(self)
        self._preview_box.pack(side="bottom", fill="both", expand=True)

        self._image_label = tk.Label(
            self._preview_box,
            text="(કોઈ ફાઇલ પસંદ નથી)\n\nClaude saves charts & files here.",
            anchor="center", font=gu_font,
            background=_PREVIEW_BG, foreground=_PREVIEW_FG,
            borderwidth=0, relief="flat",
        )
        self._image_label.pack(fill="both", expand=True)
        self._preview = self._image_label  # back-compat for existing methods
        self._html_frame = None  # lazily created on first HTML preview

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
        self._render_preview(path)

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        self._render_preview(Path(sel[0]))

    def _render_preview(self, path: Path) -> None:
        ext = path.suffix.lower()
        if ext in _IMAGE_EXTS:
            self._show_image(path)
        elif ext in _HTML_EXTS:
            self._show_html(path)
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

    def _pack_image_label(self) -> None:
        """Make the image/text Label the active preview widget."""
        if self._html_frame is not None:
            self._html_frame.pack_forget()
        if not self._image_label.winfo_ismapped():
            self._image_label.pack(fill="both", expand=True)

    def _show_image(self, path: Path) -> None:
        self._pack_image_label()
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self._image_label.configure(image="", text="(Pillow not installed)")
            self._preview_image_ref = None
            return
        try:
            img = Image.open(path)
            img.thumbnail((460, 300))
            tk_img = ImageTk.PhotoImage(img)
            self._image_label.configure(image=tk_img, text="")
            self._preview_image_ref = tk_img
        except Exception as exc:
            self._image_label.configure(image="", text=f"Cannot preview: {exc}")
            self._preview_image_ref = None

    def _show_html(self, path: Path) -> None:
        """Render an HTML or SVG file inline using tkinterweb. Falls back to
        the no-preview placeholder if tkinterweb isn't available."""
        try:
            from tkinterweb import HtmlFrame
        except ImportError:
            self._show_no_preview(path)
            self._image_label.configure(
                text=f"{path.name}\n\n(tkinterweb not installed — Open to view in browser)"
            )
            return
        if self._html_frame is None:
            try:
                self._html_frame = HtmlFrame(
                    self._preview_box, messages_enabled=False, vertical_scrollbar=True,
                )
            except Exception as exc:
                self._show_no_preview(path)
                self._image_label.configure(text=f"HTML viewer init failed: {exc}")
                return
        # Swap widgets
        if self._image_label.winfo_ismapped():
            self._image_label.pack_forget()
        if not self._html_frame.winfo_ismapped():
            self._html_frame.pack(fill="both", expand=True)
        try:
            self._html_frame.load_file(str(path))
        except Exception as exc:
            self._pack_image_label()
            self._image_label.configure(image="", text=f"Cannot render HTML: {exc}")
            self._preview_image_ref = None

    def _show_no_preview(self, path: Path) -> None:
        self._pack_image_label()
        self._image_label.configure(
            image="",
            text=f"{path.name}\n\n(Double-click or Open ⤴ to view)",
        )
        self._preview_image_ref = None
