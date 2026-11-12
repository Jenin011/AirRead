"""
fixedupload.py  –  Fixed File Upload: Text to Voice
====================================================
A native desktop application built with pywebview.
Opens a real application window — no browser or localhost server required.

Run:
    .venv\\Scripts\\python.exe fixedupload.py

Dependencies:
    pip install pywebview PyPDF2 python-docx gtts
"""

import os
import io
import uuid
import math
import base64
import shutil
import threading

import webview  # pip install pywebview

# ── optional deps (gracefully missing) ───────────────────────────────────────
try:
    import PyPDF2
    _HAS_PYPDF2 = True
except ImportError:
    _HAS_PYPDF2 = False

try:
    import docx as python_docx
    _HAS_DOCX = True
except ImportError:
    _HAS_DOCX = False

try:
    from gtts import gTTS
    _HAS_GTTS = True
except ImportError:
    _HAS_GTTS = False

try:
    import pyttsx3
    _HAS_PYTTSX3 = True
except ImportError:
    _HAS_PYTTSX3 = False

# ── directories ──────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Python API exposed to JavaScript ─────────────────────────────────────────
class AppAPI:
    """
    Every public method here becomes callable from JavaScript as:
        await window.pywebview.api.method_name(...)
    """

    # ------------------------------------------------------------------
    def get_deps(self):
        """Return which optional dependencies are available."""
        return {
            "PyPDF2":     _HAS_PYPDF2,
            "python_docx": _HAS_DOCX,
            "gtts":       _HAS_GTTS,
            "pyttsx3":    _HAS_PYTTSX3,
        }

    # ------------------------------------------------------------------
    def process_file(self, filename: str, content_b64: str) -> dict:
        """
        Receive a base64-encoded file from JS, extract its text.
        Returns { success, text, wordCount, estimatedReadingTime } or { success, error }.
        """
        try:
            raw  = base64.b64decode(content_b64)
            ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

            text = ""

            if ext == "txt":
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="replace")

            elif ext == "pdf":
                if not _HAS_PYPDF2:
                    return {"success": False, "error": "PyPDF2 not installed. Run: pip install PyPDF2"}
                reader = PyPDF2.PdfReader(io.BytesIO(raw))
                pages  = [p.extract_text() for p in reader.pages if p.extract_text()]
                text   = "\n\n".join(pages)

            elif ext == "docx":
                if not _HAS_DOCX:
                    return {"success": False, "error": "python-docx not installed. Run: pip install python-docx"}
                doc  = python_docx.Document(io.BytesIO(raw))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

            else:
                return {"success": False, "error": f"Unsupported file type: .{ext}"}

            if not text.strip():
                return {"success": False, "error": "No readable text found in the file."}

            words        = len(text.split())
            reading_time = math.ceil(words / 150)
            return {
                "success":             True,
                "text":                text,
                "wordCount":           words,
                "estimatedReadingTime": reading_time,
            }

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    def generate_mp3(self, text: str, _rate: float = 1.0, _pitch: float = 1.0) -> dict:
        """
        Generate an MP3 from text. Priority: pyttsx3 (local, fast), gTTS (web, high quality).
        Respects the _rate parameter.
        """
        if not _HAS_PYTTSX3 and not _HAS_GTTS:
            return {"success": False, "error": "No TTS engine installed (gTTS or pyttsx3)."}
        if not text.strip():
            return {"success": False, "error": "No text provided."}

        tmp_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        tmp_path = os.path.join(UPLOAD_DIR, tmp_name)

        try:
            if _HAS_PYTTSX3:
                # Local generation (Fast)
                engine = pyttsx3.init()
                # Default rate is typically 200. Scale based on _rate (0.5 to 2.0)
                engine.setProperty('rate', int(200 * _rate))
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                # Some engines might not save as .mp3 directly but .wav. 
                # pyttsx3 on Windows usually uses SAPI5 which handles naming well,
                # but we should ensure the file exists.
            else:
                # Web fallback (Slow)
                tts = gTTS(text=text, lang="en", slow=False)
                tts.save(tmp_path)

            if not os.path.exists(tmp_path):
                return {"success": False, "error": "TTS engine failed to produce file."}

            # Open native Save-As dialog
            save_targets = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory   = os.path.expanduser("~\\Desktop"),
                save_filename = "text_to_voice.mp3",
            )

            if save_targets:
                dest = save_targets[0] if isinstance(save_targets, (list, tuple)) else save_targets
                shutil.copy(tmp_path, dest)
                os.remove(tmp_path)
                return {"success": True, "saved_to": dest}
            else:
                os.remove(tmp_path)
                return {"success": False, "error": "Save cancelled."}

        except Exception as exc:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            return {"success": False, "error": str(exc)}


# ── Embedded HTML ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Text to Voice</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-primary: #ffffff; --bg-secondary: #f3f4f6; --bg-tertiary: #e5e7eb;
            --text-primary: #1f2937; --accent: #3b82f6; --border: #d1d5db;
            --shadow: rgba(0,0,0,0.1);
        }
        [data-theme="dark"] {
            --bg-primary: #1f2937; --bg-secondary: #111827; --bg-tertiary: #374151;
            --text-primary: #f9fafb; --border: #4b5563; --shadow: rgba(0,0,0,0.3);
        }
        * { box-sizing: border-box; }
        body { background: var(--bg-primary); color: var(--text-primary);
               font-family: 'Segoe UI', sans-serif; margin: 0;
               transition: background 0.3s, color 0.3s; }

        .glass { background: var(--bg-secondary); border: 1px solid var(--border);
                 box-shadow: 0 4px 20px var(--shadow); border-radius: 14px; padding: 20px; }

        .control-btn {
            background: var(--bg-tertiary); border: 1px solid var(--border);
            color: var(--text-primary); border-radius: 10px; padding: 10px 14px;
            font-weight: 600; cursor: pointer; transition: all .25s; display: flex;
            align-items: center; justify-content: center; gap: 6px;
        }
        .control-btn:hover:not(:disabled) {
            background: var(--accent); color: white; transform: scale(1.04);
        }
        .control-btn:disabled { opacity: .4; cursor: not-allowed; }

        /* drag-drop */
        .drop-zone {
            border: 2px dashed var(--border); border-radius: 12px;
            padding: 36px; text-align: center; cursor: pointer;
            transition: all .3s; background: var(--bg-secondary);
        }
        .drop-zone:hover, .drop-zone.over {
            border-color: var(--accent); background: var(--bg-tertiary);
        }
        .drop-zone.over { transform: scale(1.02); }

        .choose-btn {
            background: var(--accent); color: white; padding: 10px 22px;
            border-radius: 8px; font-weight: 600; display: inline-block;
            margin-top: 14px; cursor: pointer; transition: all .25s;
        }
        .choose-btn:hover { background: #2563eb; transform: translateY(-2px); }

        /* slider */
        input[type=range] { -webkit-appearance: none; width: 100%;
            height: 6px; border-radius: 3px; background: var(--border); outline: none; }
        input[type=range]::-webkit-slider-thumb {
            -webkit-appearance: none; width: 20px; height: 20px;
            border-radius: 50%; background: var(--accent); cursor: pointer;
        }

        /* spinner */
        .spinner { border: 3px solid var(--border); border-top-color: var(--accent);
                   border-radius: 50%; width: 48px; height: 48px;
                   animation: spin 1s linear infinite; margin: 0 auto 16px; }
        @keyframes spin { to { transform: rotate(360deg); } }

        #overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5);
                   display: flex; align-items: center; justify-content: center; z-index: 99; }
        #overlay.hidden { display: none; }

        select, textarea {
            background: var(--bg-primary); color: var(--text-primary);
            border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px;
            width: 100%; outline: none; transition: border-color .2s;
        }
        select:focus, textarea:focus { border-color: var(--accent); }
        textarea { resize: vertical; line-height: 1.6; }

        header { background: var(--bg-secondary); border-bottom: 1px solid var(--border);
                 padding: 14px 24px; display: flex; align-items: center;
                 justify-content: space-between; position: sticky; top: 0; z-index: 10; }

        .badge { background: var(--accent); color: white; border-radius: 12px;
                 padding: 2px 10px; font-size: 12px; font-weight: 600; }

        /* status dot */
        .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
        .dot.green { background: #22c55e; } .dot.red { background: #ef4444; }
        .dot.yellow { background: #eab308; }
    </style>
</head>
<body>

<!-- HEADER -->
<header>
    <div style="display:flex;align-items:center;gap:12px">
        <i class="fas fa-microphone-alt" style="font-size:22px;color:#3b82f6"></i>
        <span style="font-size:18px;font-weight:700;background:linear-gradient(to right,#3b82f6,#9333ea);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent">
            Fixed File Upload – Text to Voice
        </span>
        <span class="badge">Desktop App</span>
    </div>
    <button id="theme-btn" class="control-btn" style="width:auto;padding:8px 14px">
        <i class="fas fa-moon" id="theme-icon"></i>
    </button>
</header>

<!-- MAIN -->
<div style="max-width:1200px;margin:0 auto;padding:24px;display:grid;grid-template-columns:1fr 320px;gap:24px">

    <!-- LEFT -->
    <div style="display:flex;flex-direction:column;gap:20px">

        <!-- Upload -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-upload" style="color:#3b82f6"></i> Upload Document
            </h2>
            <div class="drop-zone" id="drop-zone">
                <i class="fas fa-cloud-upload-alt" style="font-size:42px;color:#9ca3af;margin-bottom:10px"></i>
                <p style="font-size:17px;font-weight:600;margin:0 0 4px">Drag &amp; Drop your file here</p>
                <p style="font-size:13px;color:#6b7280;margin:0">or click below to browse</p>
                <input type="file" id="file-input" style="display:none" accept=".pdf,.txt,.docx">
                <div class="choose-btn" onclick="document.getElementById('file-input').click()">
                    <i class="fas fa-folder-open" style="margin-right:6px"></i>Choose File
                </div>
            </div>
            <div id="file-info" style="display:none;margin-top:14px;padding:12px 16px;
                 background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        <p style="margin:0;font-weight:600;color:#2563eb">
                            <i class="fas fa-file" style="margin-right:6px"></i>
                            <span id="fname"></span>
                        </p>
                        <p style="margin:4px 0 0;font-size:13px;color:#4b5563">
                            <span id="fsize"></span> &nbsp;|&nbsp; <span id="ftype"></span>
                        </p>
                    </div>
                    <button onclick="clearFile()"
                        style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:18px">
                        <i class="fas fa-times-circle"></i>
                    </button>
                </div>
            </div>
            <p style="font-size:13px;color:#6b7280;margin:12px 0 0">
                <i class="fas fa-info-circle" style="margin-right:4px"></i>
                Supported: PDF, TXT, DOCX (max 10 MB)
            </p>
        </div>

        <!-- Text -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-keyboard" style="color:#3b82f6"></i> Text Content
            </h2>
            <textarea id="text-area" rows="10"
                placeholder="Text appears here after uploading a file — or type / paste directly…"></textarea>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
                <span style="font-size:13px;color:#6b7280">
                    <span id="char-count">0</span> chars &nbsp;|&nbsp;
                    <span id="word-count">0</span> words &nbsp;|&nbsp;
                    ~<span id="read-time">0</span> min read
                </span>
                <div style="display:flex;gap:8px">
                    <button onclick="clearText()"
                        style="background:#ef4444;color:white;border:none;padding:8px 16px;
                               border-radius:8px;cursor:pointer;font-weight:600">
                        <i class="fas fa-trash" style="margin-right:6px"></i>Clear
                    </button>
                    <button onclick="loadSample()"
                        style="background:#22c55e;color:white;border:none;padding:8px 16px;
                               border-radius:8px;cursor:pointer;font-weight:600">
                        <i class="fas fa-vial" style="margin-right:6px"></i>Sample Text
                    </button>
                </div>
            </div>
        </div>
    </div><!-- /left -->

    <!-- RIGHT -->
    <div style="display:flex;flex-direction:column;gap:20px">

        <!-- Voice settings -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-sliders-h" style="color:#3b82f6"></i> Voice Settings
            </h2>
            <label style="font-size:13px;font-weight:600">Voice</label>
            <select id="voice-select" style="margin-top:6px;margin-bottom:14px">
                <option value="">Default Voice</option>
            </select>

            <label style="font-size:13px;font-weight:600">
                Speed: <span id="speed-val" style="color:#3b82f6">1.0x</span>
            </label>
            <input type="range" id="speed" min="0.5" max="2.0" step="0.1" value="1.0"
                style="margin:8px 0 14px">

            <label style="font-size:13px;font-weight:600">
                Pitch: <span id="pitch-val" style="color:#3b82f6">1.0x</span>
            </label>
            <input type="range" id="pitch" min="0.5" max="2.0" step="0.1" value="1.0"
                style="margin:8px 0 0">
        </div>

        <!-- Playback -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-microphone" style="color:#3b82f6"></i> Playback
            </h2>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <button class="control-btn" id="speak-btn">
                    <i class="fas fa-play"></i> Speak
                </button>
                <button class="control-btn" id="pause-btn">
                    <i class="fas fa-pause"></i> Pause
                </button>
                <button class="control-btn" id="resume-btn">
                    <i class="fas fa-play"></i> Resume
                </button>
                <button class="control-btn" id="stop-btn">
                    <i class="fas fa-stop"></i> Stop
                </button>
            </div>
        </div>

        <!-- Export -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-download" style="color:#3b82f6"></i> Export
            </h2>
            <button class="control-btn" id="mp3-btn" style="width:100%">
                <i class="fas fa-file-audio"></i> Save as MP3
            </button>
        </div>

        <!-- Status -->
        <div class="glass">
            <h2 style="margin:0 0 14px;display:flex;align-items:center;gap:8px">
                <i class="fas fa-info-circle" style="color:#3b82f6"></i> Status
            </h2>
            <div style="font-size:13px;display:flex;flex-direction:column;gap:8px">
                <div style="display:flex;justify-content:space-between">
                    <span>Text Length:</span>
                    <span id="st-chars" style="color:#6b7280">0 chars</span>
                </div>
                <div style="display:flex;justify-content:space-between">
                    <span>PDF support:</span>
                    <span id="st-pdf">…</span>
                </div>
                <div style="display:flex;justify-content:space-between">
                    <span>DOCX support:</span>
                    <span id="st-docx">…</span>
                </div>
                <div style="display:flex;justify-content:space-between">
                    <span>MP3 export:</span>
                    <span id="st-gtts">…</span>
                </div>
            </div>
        </div>

    </div><!-- /right -->
</div><!-- /main grid -->

<!-- LOADING OVERLAY -->
<div id="overlay" class="hidden">
    <div class="glass" style="min-width:300px;text-align:center;padding:36px">
        <div class="spinner"></div>
        <p id="overlay-msg" style="font-size:16px;font-weight:600;margin:0">Processing…</p>
    </div>
</div>

<script>
// ── state ─────────────────────────────────────────────────────────────────────
let currentText = '';
const synth = window.speechSynthesis;
let speaking = false, paused = false;

// ── init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    loadVoices();
    setupListeners();
    applyTheme();
    updateBtns();

    // Query Python for dep status
    try {
        const deps = await window.pywebview.api.get_deps();
        setDepStatus('st-pdf',  deps.PyPDF2);
        setDepStatus('st-docx', deps.python_docx);
        setDepStatus('st-gtts', deps.gtts || deps.pyttsx3); // Update export status
    } catch(e) {
        ['st-pdf','st-docx','st-gtts'].forEach(id => setDepStatus(id, false));
    }
});

function setDepStatus(id, ok) {
    const el = document.getElementById(id);
    el.innerHTML = ok
        ? '<span class="dot green"></span> Available'
        : '<span class="dot red"></span> Not installed';
}

// ── voices ────────────────────────────────────────────────────────────────────
function loadVoices() {
    const fill = () => {
        const voices = synth.getVoices();
        const sel = document.getElementById('voice-select');
        sel.innerHTML = '<option value="">Default Voice</option>';
        voices.filter(v => v.lang.startsWith('en')).forEach((v, i) => {
            const o = document.createElement('option');
            o.value = i; o.textContent = `${v.name} (${v.lang})`;
            sel.appendChild(o);
        });
    };
    fill();
    synth.onvoiceschanged = fill;
}

// ── listeners ─────────────────────────────────────────────────────────────────
function setupListeners() {
    document.getElementById('theme-btn').onclick = toggleTheme;

    // drag & drop
    const zone = document.getElementById('drop-zone');
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('over'); });
    zone.addEventListener('dragleave', e => { e.preventDefault(); zone.classList.remove('over'); });
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('over');
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });
    document.getElementById('file-input').onchange = e => {
        if (e.target.files[0]) handleFile(e.target.files[0]);
    };

    // text
    document.getElementById('text-area').addEventListener('input', () => {
        currentText = document.getElementById('text-area').value;
        updateStats(); updateBtns();
    });

    // playback
    document.getElementById('speak-btn').onclick  = doSpeak;
    document.getElementById('pause-btn').onclick  = () => { paused = true;  synth.pause();  updateBtns(); };
    document.getElementById('resume-btn').onclick = () => { paused = false; synth.resume(); updateBtns(); };
    document.getElementById('stop-btn').onclick   = doStop;

    // sliders
    document.getElementById('speed').oninput = e =>
        document.getElementById('speed-val').textContent = (+e.target.value).toFixed(1) + 'x';
    document.getElementById('pitch').oninput = e =>
        document.getElementById('pitch-val').textContent = (+e.target.value).toFixed(1) + 'x';

    // export
    document.getElementById('mp3-btn').onclick = doSaveMP3;
}

// ── file handling (read → base64 → Python API) ────────────────────────────────
function handleFile(file) {
    const validExt = /\.(pdf|txt|docx)$/i;
    if (!validExt.test(file.name)) { alert('❌ Only PDF, TXT or DOCX files are supported.'); return; }
    if (file.size > 10 * 1024 * 1024) { alert('❌ File too large (max 10 MB).'); return; }

    document.getElementById('fname').textContent = file.name;
    document.getElementById('fsize').textContent = fmtSize(file.size);
    document.getElementById('ftype').textContent = file.name.split('.').pop().toUpperCase();
    document.getElementById('file-info').style.display = 'block';

    showOverlay('Reading and extracting text…');

    const reader = new FileReader();
    reader.onload = async e => {
        // strip the data-URL prefix and keep only base64
        const b64 = e.target.result.split(',')[1];
        try {
            const res = await window.pywebview.api.process_file(file.name, b64);
            hideOverlay();
            if (res.success) {
                document.getElementById('text-area').value = res.text;
                currentText = res.text;
                updateStats(); updateBtns();
                alert(`✅ File loaded!\n\nWords: ${res.wordCount}\nEst. reading time: ~${res.estimatedReadingTime} min`);
            } else {
                alert('❌ ' + res.error);
            }
        } catch(err) {
            hideOverlay();
            alert('❌ Error calling Python API: ' + err);
        }
    };
    reader.readAsDataURL(file);
}

function clearFile() {
    document.getElementById('file-input').value = '';
    document.getElementById('file-info').style.display = 'none';
}

function fmtSize(b) {
    if (!b) return '0 B';
    const u = ['B','KB','MB','GB'], i = Math.floor(Math.log(b)/Math.log(1024));
    return (b/Math.pow(1024,i)).toFixed(2) + ' ' + u[i];
}

// ── text helpers ──────────────────────────────────────────────────────────────
function updateStats() {
    const c = currentText.length;
    const w = currentText.split(/\s+/).filter(x => x).length;
    document.getElementById('char-count').textContent = c;
    document.getElementById('word-count').textContent = w;
    document.getElementById('read-time').textContent  = Math.ceil(w/150);
    document.getElementById('st-chars').textContent   = c + ' chars';
}
function clearText() {
    document.getElementById('text-area').value = ''; currentText = '';
    updateStats(); updateBtns();
}
function loadSample() {
    const s = 'Hello! This is the Text-to-Voice desktop app. Upload a PDF, TXT or DOCX file, then click Speak to hear it — or click Save as MP3 to generate an audio file.';
    document.getElementById('text-area').value = s; currentText = s;
    updateStats(); updateBtns();
}

// ── speech ────────────────────────────────────────────────────────────────────
function doSpeak() {
    if (!currentText.trim()) return;
    if (speaking) synth.cancel();
    const voices   = synth.getVoices();
    const voiceIdx = document.getElementById('voice-select').value;
    const rate  = +document.getElementById('speed').value;
    const pitch = +document.getElementById('pitch').value;
    const sents = currentText.split(/[.!?]+/).filter(s => s.trim());

    speaking = true; paused = false; updateBtns();
    let i = 0;
    (function next() {
        if (i >= sents.length) { speaking = false; updateBtns(); return; }
        if (paused) return;
        const u = new SpeechSynthesisUtterance(sents[i]);
        if (voiceIdx && voices[voiceIdx]) u.voice = voices[voiceIdx];
        u.rate = rate; u.pitch = pitch; u.volume = 1;
        u.onend   = () => { i++; setTimeout(next, 60); };
        u.onerror = ()  => { speaking = false; updateBtns(); };
        synth.speak(u);
    })();
}
function doStop() { synth.cancel(); speaking = false; paused = false; updateBtns(); }

// ── MP3 export (calls Python, opens native Save dialog) ───────────────────────
async function doSaveMP3() {
    if (!currentText.trim()) { alert('No text to convert.'); return; }
    showOverlay('Generating MP3… (this may take a moment)');
    try {
        const rate  = +document.getElementById('speed').value;
        const pitch = +document.getElementById('pitch').value;
        const res   = await window.pywebview.api.generate_mp3(currentText, rate, pitch);
        hideOverlay();
        if (res.success) {
            alert('✅ MP3 saved to:\n' + res.saved_to);
        } else {
            alert('❌ ' + res.error);
        }
    } catch(err) {
        hideOverlay();
        alert('❌ Error: ' + err);
    }
}

// ── buttons ───────────────────────────────────────────────────────────────────
function updateBtns() {
    const has = currentText.trim().length > 0;
    const s = speaking, p = paused;
    btn('speak-btn').disabled  = !has || (s && !p);
    btn('pause-btn').disabled  = !(s && !p);
    btn('resume-btn').disabled = !(s && p);
    btn('stop-btn').disabled   = !s;
    btn('mp3-btn').disabled    = !has;
}
function btn(id) { return document.getElementById(id); }

// ── overlay ───────────────────────────────────────────────────────────────────
function showOverlay(msg) {
    document.getElementById('overlay-msg').textContent = msg;
    document.getElementById('overlay').classList.remove('hidden');
}
function hideOverlay() { document.getElementById('overlay').classList.add('hidden'); }

// ── theme ─────────────────────────────────────────────────────────────────────
function toggleTheme() {
    const t = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('theme', t);
    document.getElementById('theme-icon').className = t === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
}
function applyTheme() {
    const t = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', t);
    document.getElementById('theme-icon').className = t === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
}
</script>
</body>
</html>
"""


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api = AppAPI()

    window = webview.create_window(
        title       = "Fixed File Upload – Text to Voice",
        html        = HTML,
        js_api      = api,
        width       = 1280,
        height      = 820,
        min_size    = (900, 600),
        resizable   = True,
    )

    print("Starting Text-to-Voice desktop application…")
    webview.start(debug=False)   # set debug=True to open DevTools inside the window
