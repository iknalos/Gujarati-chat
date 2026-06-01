/* GujaratiClaude webapp client.
 *
 * Talks to the FastAPI server over /ws. Renders chat with markdown +
 * syntax highlighting, streams assistant tokens into a single growing
 * bubble per turn, and shows the outputs/ folder in the right pane.
 */

// ---- highlight.js setup ----
if (window.hljs) {
  hljs.registerLanguage("python", window.hljs.python || (() => ({})));
  hljs.registerLanguage("javascript", window.hljs.javascript || (() => ({})));
  hljs.registerLanguage("typescript", window.hljs.typescript || (() => ({})));
  hljs.registerLanguage("bash", window.hljs.bash || (() => ({})));
  hljs.registerLanguage("json", window.hljs.json || (() => ({})));
  hljs.registerLanguage("xml", window.hljs.xml || (() => ({})));
  hljs.registerLanguage("css", window.hljs.css || (() => ({})));
}

// ---- marked.js setup ----
if (window.marked) {
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
}

// ---- DOM refs ----
const els = {
  messages:    document.getElementById("messages"),
  welcome:     document.querySelector(".welcome"),
  input:       document.getElementById("text-input"),
  form:        document.getElementById("input-form"),
  sendBtn:     document.getElementById("send-btn"),
  clearBtn:    document.getElementById("clear-btn"),
  fileList:    document.getElementById("file-list"),
  preview:     document.getElementById("preview"),
  refreshBtn:  document.getElementById("refresh-outputs"),
  stateDot:    document.getElementById("state-dot"),
  stateLabel:  document.getElementById("state-label"),
};

const STATE_LABELS = {
  idle:      "નિષ્ક્રિય",
  thinking:  "વિચારી રહ્યું છે",
  listening: "સાંભળી રહ્યું છે",
  speaking:  "બોલી રહ્યું છે",
};

function setState(name) {
  els.stateDot.classList.remove("idle", "thinking", "listening", "speaking");
  els.stateDot.classList.add(name);
  els.stateLabel.textContent = STATE_LABELS[name] || name;
}

// Hide welcome banner once any message is added
function hideWelcome() {
  if (els.welcome) {
    els.welcome.style.display = "none";
  }
}

// Track the currently-streaming assistant bubble + its accumulated raw text
let currentAssistant = null;     // { bubble: HTMLElement, raw: string }

function appendUser(text) {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  els.messages.appendChild(wrap);
  scrollToBottom();
}

function appendAssistantChunk(text) {
  hideWelcome();
  if (!currentAssistant) {
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    wrap.appendChild(bubble);
    els.messages.appendChild(wrap);
    currentAssistant = { bubble, raw: "" };
  }
  // The server emits a sentence at a time (post-filter). Add it with a
  // space so paragraphs flow naturally.
  if (currentAssistant.raw && !currentAssistant.raw.endsWith("\n")) {
    currentAssistant.raw += " ";
  }
  currentAssistant.raw += text;
  renderAssistantMarkdown();
  scrollToBottom();
}

function renderAssistantMarkdown() {
  if (!currentAssistant) return;
  const html = window.marked ? marked.parse(currentAssistant.raw) : escapeHtml(currentAssistant.raw);
  currentAssistant.bubble.innerHTML = html;
  // Apply syntax highlighting to any new <pre><code> elements
  if (window.hljs) {
    currentAssistant.bubble.querySelectorAll("pre code").forEach((el) => {
      try { hljs.highlightElement(el); } catch (e) {}
    });
  }
}

function appendTool(text) {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg tool";
  wrap.textContent = text;
  els.messages.appendChild(wrap);
  scrollToBottom();
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
  ));
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

// ---- WebSocket protocol ----
let ws = null;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    setState("idle");
  };

  ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }
    handleServerMessage(msg);
  };

  ws.onclose = () => {
    setState("idle");
    appendTool("[disconnected — reconnecting in 2s]");
    setTimeout(connect, 2000);
  };

  ws.onerror = () => {
    // onclose will fire too
  };
}

function handleServerMessage(msg) {
  switch (msg.type) {
    case "ready":
      // Server tells us project_dir, outputs_dir — could display
      refreshOutputs();
      // Load and replay history
      fetchHistory();
      break;
    case "history": // legacy
    case "transcript":
      if (msg.role === "user") {
        appendUser(msg.text);
      } else if (msg.role === "assistant") {
        setState("thinking");
        appendAssistantChunk(msg.text);
      } else if (msg.role === "tool") {
        appendTool(msg.text);
      }
      break;
    case "turn_end":
      // Finalize current assistant bubble
      if (currentAssistant) {
        renderAssistantMarkdown();
        currentAssistant = null;
      }
      setState("idle");
      refreshOutputs();
      break;
    case "cleared":
      // Wipe DOM, reset state
      els.messages.innerHTML = "";
      currentAssistant = null;
      hideWelcomeReset();
      setState("idle");
      break;
    case "error":
      appendTool(`[server error: ${msg.message}]`);
      break;
    default:
      // ignore unknown
      break;
  }
}

function hideWelcomeReset() {
  // After clear, re-show a short reset banner (welcome stays gone)
  appendTool("── વાતચીત સાફ થઈ — fresh start ──");
}

async function fetchHistory() {
  try {
    const r = await fetch("/api/history");
    const j = await r.json();
    if (j.transcript && j.transcript.length > 0) {
      hideWelcome();
      // Replay as a faint header + entries
      appendTool("── પાછલી વાતચીત / previous conversation ──");
      for (const e of j.transcript) {
        if (e.role === "user")       appendUser(e.text);
        else if (e.role === "assistant") {
          // For history replay, render each saved entry as its own bubble
          const wrap = document.createElement("div");
          wrap.className = "msg assistant";
          const bubble = document.createElement("div");
          bubble.className = "bubble";
          bubble.innerHTML = window.marked ? marked.parse(e.text) : escapeHtml(e.text);
          if (window.hljs) {
            bubble.querySelectorAll("pre code").forEach(el => {
              try { hljs.highlightElement(el); } catch (err) {}
            });
          }
          wrap.appendChild(bubble);
          els.messages.appendChild(wrap);
        }
        else                          appendTool(e.text);
      }
      appendTool("── નવી વાતચીત / new conversation ──");
      scrollToBottom();
    }
  } catch (e) {
    // Non-fatal
  }
}

// ---- Input handling ----
function submitInput() {
  const text = els.input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "user_message", text }));
  els.input.value = "";
  autoresize();
  setState("thinking");
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  submitInput();
});

els.input.addEventListener("keydown", (e) => {
  // Enter to send, Shift+Enter for new line
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitInput();
  }
});

function autoresize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
}
els.input.addEventListener("input", autoresize);

els.clearBtn.addEventListener("click", () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (confirm("આખી વાતચીત સાફ કરવી? Claude પણ બધું ભૂલી જશે.")) {
    ws.send(JSON.stringify({ type: "clear" }));
  }
});

// ---- Outputs pane ----
let selectedFile = null;
async function refreshOutputs() {
  try {
    const r = await fetch("/api/outputs");
    const j = await r.json();
    renderFileList(j.files || []);
  } catch (e) {
    // ignore
  }
}

function renderFileList(files) {
  const previouslySelected = selectedFile;
  els.fileList.innerHTML = "";
  for (const f of files) {
    const li = document.createElement("li");
    li.dataset.url = f.url;
    li.dataset.ext = f.ext;
    li.dataset.name = f.name;
    li.innerHTML = `
      <span class="name">${iconForExt(f.ext)}  ${escapeHtml(f.name)}</span>
      <span class="size">${fmtSize(f.size)}</span>
    `;
    li.addEventListener("click", () => previewFile(f));
    if (previouslySelected === f.url) li.classList.add("selected");
    els.fileList.appendChild(li);
  }
  // If nothing selected yet AND list is non-empty, auto-preview first
  if (!previouslySelected && files.length > 0) {
    previewFile(files[0]);
  }
}

function previewFile(f) {
  selectedFile = f.url;
  // Update selected styling
  els.fileList.querySelectorAll("li").forEach(li => {
    li.classList.toggle("selected", li.dataset.url === f.url);
  });

  const ext = f.ext;
  if ([".png",".jpg",".jpeg",".gif",".bmp",".webp"].includes(ext)) {
    els.preview.innerHTML = `<img src="${f.url}?t=${Date.now()}" alt="${escapeHtml(f.name)}">`;
  } else if ([".html",".htm",".svg"].includes(ext)) {
    els.preview.innerHTML = `<iframe src="${f.url}?t=${Date.now()}" sandbox="allow-scripts allow-same-origin"></iframe>`;
  } else if (ext === ".csv" || ext === ".tsv") {
    renderCsvPreview(f);
  } else if ([".txt",".md",".log",".json",".yaml",".yml",".py",".js",".ts",".css"].includes(ext)) {
    renderTextPreview(f);
  } else {
    els.preview.innerHTML = `
      <div class="preview-empty">
        ${escapeHtml(f.name)}<br>
        (Open in OS app via Outputs folder)
      </div>`;
  }
}

async function renderCsvPreview(f) {
  try {
    const r = await fetch(f.url);
    const text = await r.text();
    const sep = f.ext === ".tsv" ? "\t" : ",";
    const lines = text.split(/\r?\n/).slice(0, 200);
    let html = "<table><thead><tr>";
    const head = lines.shift().split(sep);
    for (const h of head) html += `<th>${escapeHtml(h)}</th>`;
    html += "</tr></thead><tbody>";
    for (const line of lines) {
      if (!line.trim()) continue;
      html += "<tr>";
      for (const cell of line.split(sep)) html += `<td>${escapeHtml(cell)}</td>`;
      html += "</tr>";
    }
    html += "</tbody></table>";
    els.preview.innerHTML = html;
  } catch (e) {
    els.preview.innerHTML = `<div class="preview-empty">Cannot read ${escapeHtml(f.name)}</div>`;
  }
}

async function renderTextPreview(f) {
  try {
    const r = await fetch(f.url);
    const text = await r.text();
    const lang = f.ext.slice(1);
    const escaped = escapeHtml(text);
    els.preview.innerHTML = `<pre style="white-space:pre-wrap;width:100%;height:100%;overflow:auto;margin:0;font-family:Consolas,monospace;font-size:12px;background:var(--code-bg);padding:12px;border-radius:6px;"><code class="language-${lang}">${escaped}</code></pre>`;
    if (window.hljs) {
      els.preview.querySelectorAll("pre code").forEach(el => {
        try { hljs.highlightElement(el); } catch (e) {}
      });
    }
  } catch (e) {
    els.preview.innerHTML = `<div class="preview-empty">Cannot read ${escapeHtml(f.name)}</div>`;
  }
}

function iconForExt(ext) {
  if ([".png",".jpg",".jpeg",".gif",".bmp",".svg",".webp"].includes(ext)) return "🖼";
  if ([".xlsx",".xls",".csv",".tsv"].includes(ext)) return "📊";
  if ([".html",".htm"].includes(ext)) return "🌐";
  if (ext === ".pdf") return "📑";
  if ([".py"].includes(ext)) return "🐍";
  if ([".js",".ts"].includes(ext)) return "📜";
  return "📄";
}

function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n/1024)} KB`;
  return `${(n / (1024*1024)).toFixed(1)} MB`;
}

els.refreshBtn.addEventListener("click", refreshOutputs);

// Poll outputs folder every 2s for new files
setInterval(refreshOutputs, 2000);

// ---- Start ----
connect();
