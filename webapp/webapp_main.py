"""Webapp entry point.

Starts the FastAPI server in a background thread, then opens a pywebview
window pointing at it. When the window closes, the server is shut down.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

import config


def _free_port(start: int = 5174) -> int:
    for p in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def run(project_dir: Path) -> int:
    os.environ["GC_WEB_PROJECT_DIR"] = str(project_dir)
    # Make sure outputs dir exists before the watcher / browser hits it
    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Import the FastAPI app AFTER setting the env var so server.py sees it
    from webapp.server import app  # noqa: E402

    port = _free_port()
    cfg = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(cfg)

    server_thread = threading.Thread(
        target=server.run, name="gc-uvicorn", daemon=True,
    )
    server_thread.start()

    # Wait for the server to start accepting connections
    deadline = time.time() + 8
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect(("127.0.0.1", port))
                break
            except OSError:
                time.sleep(0.1)
    else:
        print(f"server failed to start on port {port}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}"
    webview.create_window(
        title="GujaratiClaude",
        url=url,
        width=1240,
        height=800,
        min_size=(900, 560),
        background_color="#1a1a1a",
    )
    try:
        webview.start()
    finally:
        server.should_exit = True
        server_thread.join(timeout=2)
    return 0
