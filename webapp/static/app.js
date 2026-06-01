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
  messages:      document.getElementById("messages"),
  welcome:       document.querySelector(".welcome"),
  input:         document.getElementById("text-input"),
  form:          document.getElementById("input-form"),
  sendBtn:       document.getElementById("send-btn"),
  clearBtn:      document.getElementById("clear-btn"),
  attachBtn:     document.getElementById("attach-btn"),
  filePicker:    document.getElementById("file-picker"),
  attachedFiles: document.getElementById("attached-files"),
  micBtn:        document.getElementById("mic-btn"),
  ttsToggle:     document.getElementById("tts-toggle"),
  fileList:      document.getElementById("file-list"),
  preview:       document.getElementById("preview"),
  refreshBtn:    document.getElementById("refresh-outputs"),
  stateDot:      document.getElementById("state-dot"),
  stateLabel:    document.getElementById("state-label"),
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
  // Feed the same chunk to TTS so Claude's speech follows the text
  bufferAndSpeak(text);
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
  const card = document.createElement("div");
  card.className = "tool-card";
  card.textContent = text;
  card.title = text;  // tooltip shows full text if truncated
  wrap.appendChild(card);
  els.messages.appendChild(wrap);
  scrollToBottom();
}

// ---- Typing indicator (pulsing dots while Claude composes) ----
let typingBubble = null;
function showTyping() {
  if (typingBubble) return;
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg typing";
  wrap.innerHTML = `
    <div class="bubble">
      <span class="typing-label">Claude વિચારી રહ્યું છે</span>
      <span class="typing-dots"><span></span><span></span><span></span></span>
    </div>`;
  els.messages.appendChild(wrap);
  typingBubble = wrap;
  scrollToBottom();
}
function hideTyping() {
  if (typingBubble) {
    typingBubble.remove();
    typingBubble = null;
  }
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
      refreshOutputs();
      fetchHistory();
      break;
    case "history":
    case "transcript":
      if (msg.role === "user") {
        // Defensive: a new user turn means any in-flight assistant bubble
        // should be considered finished, even if turn_end hasn't arrived
        // yet (race between pump_events and receive loop).
        if (currentAssistant) {
          renderAssistantMarkdown();
          currentAssistant = null;
        }
        hideTyping();
        appendUser(msg.text);
      } else if (msg.role === "assistant") {
        // First chunk of the turn — replace typing indicator with real content
        hideTyping();
        setState("thinking");
        appendAssistantChunk(msg.text);
      } else if (msg.role === "tool") {
        // Tool calls keep the typing indicator hidden but show their card
        hideTyping();
        appendTool(msg.text);
      }
      break;
    case "turn_end":
      hideTyping();
      if (currentAssistant) {
        renderAssistantMarkdown();
        currentAssistant = null;
      }
      flushTtsBuffer();   // speak any trailing tail without a terminator
      setState("idle");
      refreshOutputs();
      break;
    case "cleared":
      els.messages.innerHTML = "";
      currentAssistant = null;
      typingBubble = null;
      attachedFiles = [];
      renderAttachedFiles();
      hideWelcomeReset();
      setState("idle");
      break;
    case "error":
      hideTyping();
      appendTool(`[server error: ${msg.message}]`);
      break;
    default:
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

// ---- Attached files (paths Claude should Read) ----
let attachedFiles = [];   // [{name, path}]
function renderAttachedFiles() {
  els.attachedFiles.innerHTML = "";
  for (const [i, f] of attachedFiles.entries()) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `
      📎 <span>${escapeHtml(f.name)}</span>
      <button type="button" title="Remove" data-idx="${i}">✕</button>
    `;
    chip.querySelector("button").addEventListener("click", (e) => {
      const idx = parseInt(e.target.dataset.idx, 10);
      attachedFiles.splice(idx, 1);
      renderAttachedFiles();
    });
    els.attachedFiles.appendChild(chip);
  }
}

els.attachBtn.addEventListener("click", () => els.filePicker.click());
els.filePicker.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  // Browsers don't expose absolute paths for security. pywebview's file
  // input does expose them via the `path` property when available.
  // Fallback: use the file name and ask the user to drag the file or use
  // the file picker from the OS — this is a known browser limitation.
  const fullPath = file.path || file.webkitRelativePath || file.name;
  attachedFiles.push({ name: file.name, path: fullPath });
  renderAttachedFiles();
  els.filePicker.value = "";
});

// Drag-and-drop files onto the chat area as a richer alternative.
els.messages.addEventListener("dragover", (e) => {
  e.preventDefault();
  els.messages.style.background = "rgba(201,95,63,0.04)";
});
els.messages.addEventListener("dragleave", () => {
  els.messages.style.background = "";
});
els.messages.addEventListener("drop", (e) => {
  e.preventDefault();
  els.messages.style.background = "";
  for (const f of e.dataTransfer.files) {
    const fullPath = f.path || f.name;
    attachedFiles.push({ name: f.name, path: fullPath });
  }
  renderAttachedFiles();
});

// ---- Input handling ----
function submitInput() {
  const text = els.input.value.trim();
  if (!text && attachedFiles.length === 0) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  // Prepend attached file refs so Claude knows to Read them
  let finalText = text;
  if (attachedFiles.length > 0) {
    const refs = attachedFiles.map(f => `@${f.path}`).join(" ");
    finalText = refs + (text ? "\n\n" + text : "");
  }

  ws.send(JSON.stringify({ type: "user_message", text: finalText }));
  els.input.value = "";
  attachedFiles = [];
  renderAttachedFiles();
  autoresize();
  setState("thinking");
  showTyping();   // immediate visual feedback before any server response
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

// ---- Voice input (Web Speech API SpeechRecognition) ----
// Behavior: click the mic once to start. Speak freely — pauses are OK.
// Recognition auto-stops after SILENCE_TIMEOUT_MS of true silence (no
// new tokens arriving). Click the mic again to stop manually at any time.
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
const SILENCE_TIMEOUT_MS = 3000;
let recognition = null;
let listening = false;
let micBaseText = "";          // text already in the input when listening started
let micFinalAccum = "";        // all finalized phrases this session
let silenceTimer = null;
let stoppingManually = false;  // distinguishes user-click stop vs silence stop

if (SpeechRec) {
  recognition = new SpeechRec();
  recognition.lang = "gu-IN";
  recognition.continuous = true;        // keep going across natural pauses
  recognition.interimResults = true;

  function resetSilenceTimer() {
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (listening) {
        try { recognition.stop(); } catch (e) {}
      }
    }, SILENCE_TIMEOUT_MS);
  }

  recognition.onstart = () => {
    micFinalAccum = "";
    stoppingManually = false;
    // No silence timer yet — wait for first real result so we don't time
    // out before the user has had a chance to speak.
  };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        micFinalAccum += t + " ";
      } else {
        interim += t;
      }
    }
    const combined = [micBaseText, micFinalAccum, interim]
      .map(s => s.trim())
      .filter(Boolean)
      .join(" ");
    els.input.value = combined;
    autoresize();
    resetSilenceTimer();   // any new token resets the silence clock
  };

  recognition.onend = () => {
    clearTimeout(silenceTimer);
    listening = false;
    els.micBtn.classList.remove("listening");
    // Auto-submit if we captured new text
    if (els.input.value.trim() && els.input.value.trim() !== micBaseText.trim()) {
      setTimeout(submitInput, 250);
    }
  };

  recognition.onerror = (e) => {
    clearTimeout(silenceTimer);
    listening = false;
    els.micBtn.classList.remove("listening");
    if (e.error !== "aborted" && e.error !== "no-speech") {
      appendTool(`[mic error: ${e.error}]`);
    }
  };
} else {
  els.micBtn.disabled = true;
  els.micBtn.title = "Browser doesn't support Web Speech API";
  els.micBtn.style.opacity = "0.4";
}

els.micBtn.addEventListener("click", () => {
  if (!recognition) return;
  if (listening) {
    stoppingManually = true;
    try { recognition.stop(); } catch (e) {}
    return;
  }
  micBaseText = els.input.value;
  try {
    recognition.start();
    listening = true;
    els.micBtn.classList.add("listening");
  } catch (e) {
    // start() throws if already started — toggle off
    try { recognition.stop(); } catch (e2) {}
  }
});

// ---- Voice output (Web Speech API speechSynthesis) ----
let ttsEnabled = false;
let ttsBuffer = "";
let preferredVoice = null;

function loadVoices() {
  if (!window.speechSynthesis) return;
  const voices = speechSynthesis.getVoices();
  // Prefer an explicitly gu-IN voice; fall back to any gu-* or hi-IN
  preferredVoice =
    voices.find(v => v.lang === "gu-IN") ||
    voices.find(v => v.lang.startsWith("gu")) ||
    voices.find(v => v.lang === "hi-IN") ||
    null;
}
if (window.speechSynthesis) {
  loadVoices();
  speechSynthesis.onvoiceschanged = loadVoices;
}

function speak(text) {
  if (!ttsEnabled || !window.speechSynthesis) return;
  const clean = text.replace(/[*_`#>~|]/g, "").trim();
  if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.lang = "gu-IN";
  if (preferredVoice) u.voice = preferredVoice;
  u.rate = 1.0;
  speechSynthesis.speak(u);
}

function bufferAndSpeak(text) {
  if (!ttsEnabled) return;
  ttsBuffer += text;
  // Split on Gujarati / Latin sentence terminators.
  const parts = ttsBuffer.split(/(?<=[.।?!])\s+/);
  if (parts.length > 1) {
    for (let i = 0; i < parts.length - 1; i++) speak(parts[i]);
    ttsBuffer = parts[parts.length - 1];
  }
}

function flushTtsBuffer() {
  if (ttsBuffer.trim()) speak(ttsBuffer);
  ttsBuffer = "";
}

els.ttsToggle.addEventListener("click", () => {
  ttsEnabled = !ttsEnabled;
  els.ttsToggle.classList.toggle("active", ttsEnabled);
  els.ttsToggle.textContent = ttsEnabled ? "🔊 Speak" : "🔇 Speak";
  if (!ttsEnabled && window.speechSynthesis) {
    speechSynthesis.cancel();   // stop any in-flight speech
    ttsBuffer = "";
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
