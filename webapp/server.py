"""FastAPI server for the GujaratiClaude webapp.

One-user, localhost-only: the server holds a single ClaudeBridge instance
and brokers it to a single-page web client over a WebSocket. The bridge
behaviour is unchanged from text mode — same `claude -p` subprocess, same
system prompt, same Gujarati persona, same `--resume` session continuity.

Endpoints:
  GET  /                         → index.html
  GET  /static/<file>            → CSS / JS
  GET  /outputs/<file>           → files Claude wrote to outputs/
  GET  /api/history              → persisted transcript JSON
  GET  /api/outputs              → list outputs/ folder
  WS   /ws                       → streaming chat protocol (see app.js)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from queue import Empty

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import history as history_mod
from claude_bridge import ClaudeBridge, StreamEvent


_PROJECT_DIR = Path(
    os.environ.get("GC_WEB_PROJECT_DIR", str(config.PROJECT_DIR))
).resolve()

_history = history_mod.load()
_bridge = ClaudeBridge(
    project_dir=_PROJECT_DIR,
    system_prompt_file=config.GU_SYSTEM_PROMPT_FILE,
    claude_bin=config.CLAUDE_BIN,
    permission_mode=config.PERMISSION_MODE,
    strip_code=False,
    resume_session_id=_history.session_id,
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="GujaratiClaude")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def _prewarm_bridge() -> None:
    """Spawn the claude subprocess on server boot so the first user message
    doesn't pay the ~3-5 s cold-start cost. Failure here is non-fatal: the
    /ws handler will retry on first connection."""
    import asyncio as _aio
    try:
        await _aio.get_event_loop().run_in_executor(None, _bridge.start)
    except Exception as exc:
        print(f"prewarm failed (will retry on first WS): {exc}")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/history")
async def api_history():
    return JSONResponse({
        "session_id": _history.session_id,
        "project_dir": _history.project_dir,
        "transcript": [
            {"role": e.role, "text": e.text, "ts": e.ts}
            for e in _history.transcript
        ],
    })


@app.get("/api/outputs")
async def api_outputs():
    files = []
    if config.OUTPUTS_DIR.exists():
        try:
            entries = sorted(
                config.OUTPUTS_DIR.iterdir(),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for p in entries:
                if not p.is_file():
                    continue
                st = p.stat()
                files.append({
                    "name": p.name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "ext": p.suffix.lower(),
                    "url": f"/outputs/{p.name}",
                })
        except OSError:
            pass
    return JSONResponse({"dir": str(config.OUTPUTS_DIR), "files": files})


@app.get("/outputs/{filename}")
async def get_output(filename: str):
    safe = config.OUTPUTS_DIR / filename
    try:
        safe = safe.resolve()
        outputs_resolved = config.OUTPUTS_DIR.resolve()
    except OSError:
        return JSONResponse({"error": "not found"}, status_code=404)
    # Path traversal guard
    if outputs_resolved not in safe.parents and safe != outputs_resolved:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if not safe.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(safe))


# ---------------------------------------------------------------------------
# WebSocket — streaming chat protocol
# ---------------------------------------------------------------------------

def _format_tool_use(block: dict) -> str:
    """Same formatter as text_mode._format_tool_use — kept inline to avoid
    importing the Tkinter-coupled module."""
    name = block.get("name", "?")
    inp = block.get("input") or {}

    def short(s: str, n: int = 90) -> str:
        s = str(s).split("\n", 1)[0].strip()
        return s if len(s) <= n else s[: n - 1] + "…"

    if name == "Bash":
        return f"⚡  {short(inp.get('command', ''))}"
    if name == "Read":
        return f"📖  Read {short(inp.get('file_path', '?'), 120)}"
    if name == "Write":
        return f"✏️  Write {short(inp.get('file_path', '?'), 120)}"
    if name == "Edit":
        return f"✏️  Edit {short(inp.get('file_path', '?'), 120)}"
    if name == "Glob":
        return f"🔍  Glob {short(inp.get('pattern', '?'))}"
    if name == "Grep":
        return f"🔍  Grep {short(inp.get('pattern', '?'))}"
    if name == "LS":
        return f"📂  LS {short(inp.get('path', '?'), 120)}"
    if name == "WebSearch":
        return f"🌐  Search: {short(inp.get('query', '?'))}"
    if name == "WebFetch":
        return f"🌐  Fetch: {short(inp.get('url', '?'), 120)}"
    if name == "Task":
        return f"🤖  Task: {short(inp.get('description', '?'))}"
    return f"⚙️  {name}"


def _stream_event_to_msg(ev: StreamEvent) -> dict | None:
    if ev.kind == "text_delta":
        _history.append("assistant", ev.text)
        return {"type": "transcript", "role": "assistant", "text": ev.text}
    if ev.kind == "tool_use":
        return {
            "type": "transcript", "role": "tool",
            "text": _format_tool_use(ev.data or {}),
        }
    if ev.kind == "turn_end":
        return {"type": "turn_end"}
    if ev.kind == "error":
        d = ev.data or {}
        return {
            "type": "transcript", "role": "tool",
            "text": f"[bridge error: {d.get('message', '')}]",
        }
    return None


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global _bridge, _history
    await ws.accept()
    loop = asyncio.get_event_loop()

    # Lazy-start the bridge on first connection (so server startup is cheap)
    def _ensure_bridge():
        if _bridge._proc is None or _bridge._proc.poll() is not None:
            _bridge.start()

    await loop.run_in_executor(None, _ensure_bridge)

    # Pump bridge events to the client
    pump_running = True

    async def pump_events():
        while pump_running:
            try:
                ev = await loop.run_in_executor(
                    None, _bridge.events().get, True, 0.5
                )
            except Empty:
                continue
            except Exception as exc:
                try:
                    await ws.send_json({"type": "error", "message": str(exc)})
                except Exception:
                    return
                continue
            msg = _stream_event_to_msg(ev)
            if msg is not None:
                try:
                    await ws.send_json(msg)
                except Exception:
                    return

    pump_task = asyncio.create_task(pump_events())

    try:
        # Send a "ready" so the client can hide spinner / focus input
        await ws.send_json({
            "type": "ready",
            "project_dir": str(_PROJECT_DIR),
            "outputs_dir": str(config.OUTPUTS_DIR),
        })

        while True:
            data = await ws.receive_json()
            kind = data.get("type")

            if kind == "user_message":
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                _history.append("user", text)
                await ws.send_json({"type": "transcript", "role": "user", "text": text})
                try:
                    await loop.run_in_executor(None, _bridge.send, text)
                except Exception as exc:
                    await ws.send_json({"type": "transcript", "role": "tool",
                                        "text": f"[send failed: {exc}]"})

            elif kind == "clear":
                # Wipe persisted history + reset Claude session
                _history = history_mod.History()
                history_mod.save(_history)
                try:
                    _bridge.close()
                except Exception:
                    pass
                _bridge.resume_session_id = None
                _bridge.observed_session_id = None
                await loop.run_in_executor(None, _bridge.start)
                await ws.send_json({"type": "cleared"})

    except WebSocketDisconnect:
        pass
    finally:
        pump_running = False
        pump_task.cancel()
        # Persist whatever the bridge observed before disconnect
        if _bridge.observed_session_id:
            _history.session_id = _bridge.observed_session_id
        _history.project_dir = str(_PROJECT_DIR)
        history_mod.save(_history)
