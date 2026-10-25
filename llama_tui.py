#!/usr/bin/env python3
"""llama-tui2 — btop-style chat TUI for llama.cpp on Termux.

Usage:
    python llama-tui2.py [path/to/model.gguf]

Keys:
    Enter   send message          Ctrl+X  stop generation
    Ctrl+L  clear screen          Ctrl+R  reset conversation memory
    Ctrl+N  new session           Ctrl+S  save session
    Ctrl+Q  quit
    F1–F8   open panels (help/model/settings/stats/sessions/system/browser/cron)

Model discovery: scans $LLAMA_MODEL_DIR, ~/llama.cpp/models, ~/.llama-tui/models
(recursively, depth ≤ 2) for *.gguf. Vocab-only and tiny files (<10 MB) are
filtered out. Switch live via F2 / /model.

Optional: `pip install psutil` for per-process stats (falls back to /proc).
"""

import codecs
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from agent_bridge import PageFetcher, HarManager, OrchestratorAgent, CronStore

try:
    from textual.widgets import TextArea
    HAS_TEXTAREA = True
except Exception:
    TextArea = None
    HAS_TEXTAREA = False

try:
    import psutil
except Exception:
    psutil = None

# ───────────────────────── configuration ─────────────────────────
HOME = os.path.expanduser("~")
LLAMA_DIR = os.path.join(HOME, "llama.cpp")
LLAMA_BIN = os.environ.get("LLAMA_BIN", os.path.join(LLAMA_DIR, "build/bin/llama-cli"))

# Directories scanned for *.gguf. First match wins for display order.
MODEL_DIRS = [
    d
    for d in (
        os.environ.get("LLAMA_MODEL_DIR"),
        os.path.join(LLAMA_DIR, "models"),
        os.path.join(HOME, ".llama-tui", "models"),
    )
    if d
]

# Below this size, a .gguf is almost certainly a vocab/test file, not a model.
MIN_MODEL_BYTES = 10 * 1024 * 1024  # 10 MB

THREADS = 4
CTX = 2048
N_PREDICT = 256
TEMP = 0.7
TOP_P = 0.95
REPEAT_PENALTY = 1.1
TIMEOUT_S = 180
MAX_PROMPT_CHARS = 3200
SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and concisely."
DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT

SESS_DIR = os.path.join(HOME, ".llama-tui", "sessions")

STOP_MARKERS = ["</s>", "<|user|>", "<|assistant|>", "<|system|>", "[end of text]"]
SPARK = "▁▂▃▄▅▆▇█"

# ───────────────────────── palette ─────────────────────────
C_BORDER = "#4c566a"
C_TITLE = "#f38ba8"
C_TEXT = "#cdd6f4"
C_DIM = "#6c7086"
C_USER = "#89b4fa"
C_AI = "#a6e3a1"
C_WARN = "#f9e2af"
C_ERR = "#f38ba8"


# ───────────────────────── helpers ─────────────────────────
def gradient(frac: float) -> str:
    frac = max(0.0, min(1.0, frac))
    if frac < 0.5:
        r = int(166 + (249 - 166) * frac * 2)
        g = int(227 + (226 - 227) * frac * 2)
        b = int(161 + (175 - 161) * frac * 2)
    else:
        t = (frac - 0.5) * 2
        r = int(249 + (243 - 249) * t)
        g = int(226 + (139 - 226) * t)
        b = int(175 + (168 - 175) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def meter(pct: float, width: int) -> Text:
    width = max(4, width)
    filled = int(round(width * pct / 100.0))
    t = Text()
    for i in range(width):
        if i < filled:
            t.append("■", style=gradient(i / width))
        else:
            t.append("■", style="#313244")
    return t


def sparkline(values, width: int, vmax: float = 100.0) -> Text:
    width = max(4, width)
    vals = list(values)[-width:]
    t = Text(" " * (width - len(vals)))
    vmax = max(vmax, 1e-9)
    for v in vals:
        frac = max(0.0, min(1.0, v / vmax))
        t.append(
            SPARK[min(len(SPARK) - 1, int(frac * (len(SPARK) - 1) + 0.5))],
            style=gradient(frac),
        )
    return t


def fmt_bytes(n: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"


def quant_of(path: str) -> str:
    m = re.search(
        r"[._-](Q\d[_A-Z0-9]*|IQ\d[_A-Z0-9]*|F16|F32|BF16)",
        os.path.basename(path),
    )
    return m.group(1) if m else "?"


def is_probably_vocab(path: str) -> bool:
    """Heuristic: filename starts with ggml-vocab- OR file is < MIN_MODEL_BYTES."""
    if os.path.basename(path).lower().startswith("ggml-vocab-"):
        return True
    try:
        return os.path.getsize(path) < MIN_MODEL_BYTES
    except OSError:
        return True


def discover_models(include_tiny: bool = False) -> list:
    """Recursively find *.gguf under MODEL_DIRS (depth ≤ 2).

    Filters out vocab-only files and anything < MIN_MODEL_BYTES unless
    include_tiny is set. Deduped, sorted by filename.
    """
    seen = set()
    out = []
    for root in MODEL_DIRS:
        if not root or not os.path.isdir(root):
            continue
        base_len = len(root.rstrip(os.sep))
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[base_len:].count(os.sep)
            if depth >= 2:
                dirnames[:] = []
            for fn in filenames:
                if not fn.lower().endswith(".gguf"):
                    continue
                full = os.path.join(dirpath, fn)
                if full in seen:
                    continue
                if not include_tiny and is_probably_vocab(full):
                    continue
                seen.add(full)
                out.append(full)
    out.sort(key=lambda p: (os.path.basename(p).lower(), p))
    return out


class ModelState:
    """Mutable holder so worker threads always read the current path."""
    path = ""

    @classmethod
    def init(cls, requested: str) -> None:
        # Explicit path that looks like a real model — honor it.
        if requested and os.path.exists(requested):
            if not is_probably_vocab(requested):
                cls.path = requested
                return
            cls.path = requested
            return
        # Fall back to first real model found, prioritizing Qwen 2.5 3B if present
        found = discover_models()
        for m in found:
            if "qwen2.5-3b" in m.lower():
                cls.path = m
                return
        cls.path = found[0] if found else requested


# Resolve initial model: CLI arg > env var > first discovered > default guess
_initial = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get(
        "LLAMA_MODEL",
        os.path.join(LLAMA_DIR, "models", "qwen2.5-3b-instruct-q4_k_m.gguf"),
    )
)
ModelState.init(_initial)

MODEL_PATH = ModelState.path  # legacy alias


# ───────────────────────── prompt formatting helper ─────────────────────────
def format_chat_prompt(model_path: str, history: list, system_prompt: str) -> tuple:
    """Format prompt with the appropriate template depending on the model."""
    low = model_path.lower()
    if "qwen" in low or "deepseek" in low:
        # ChatML format
        p = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        for r, t in history:
            role = "user" if r == "user" else "assistant"
            p += f"<|im_start|>{role}\n{t}<|im_end|>\n"
        p += "<|im_start|>assistant\n"
        marker = "<|im_start|>assistant"
        stops = ["<|im_end|>", "<|im_start|>", "<|endoftext|>", "\n[ Prompt:"]
    elif "llama-3" in low or "llama3" in low:
        # Llama 3 format
        p = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
        for r, t in history:
            role = "user" if r == "user" else "assistant"
            p += f"<|start_header_id|>{role}<|end_header_id|>\n\n{t}<|eot_id|>"
        p += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        marker = "<|start_header_id|>assistant<|end_header_id|>"
        stops = ["<|eot_id|>", "<|start_header_id|>", "\n[ Prompt:"]
    else:
        # Default / TinyLlama format
        p = f"<|system|>\n{system_prompt}</s>\n"
        for r, t in history:
            role = "user" if r == "user" else "assistant"
            p += f"<|{role}|>\n{t}</s>\n"
        p += "<|assistant|>\n"
        marker = "<|assistant|>"
        stops = ["</s>", "<|user|>", "<|system|>", "<|assistant|>", "[end of text]", "\n[ Prompt:"]
    return p, marker, stops


# ───────────────────────── llama-cli flag detection ─────────────────────────
_LLAMA_FLAGS = None  # populated lazily on first call


def llama_flags() -> dict:
    """Detect flag spellings once. Different llama.cpp builds use different names.

    Returns a dict with keys:
        no_cnv:            string flag, or None to omit
        simple_io:         string flag, or None to omit
        no_display_prompt: string flag, or None to omit
    """
    global _LLAMA_FLAGS
    if _LLAMA_FLAGS is not None:
        return _LLAMA_FLAGS

    flags = {"no_cnv": "--single-turn", "simple_io": "--simple-io", "no_display_prompt": "--no-display-prompt"}
    try:
        out = subprocess.run(
            [LLAMA_BIN, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        _LLAMA_FLAGS = flags
        return flags

    # single-turn / no-conversation spelling
    if "--single-turn" in out:
        flags["no_cnv"] = "--single-turn"
    elif "-st" in out:
        flags["no_cnv"] = "-st"
    elif "--no-conversation" in out:
        flags["no_cnv"] = "--no-conversation"
    elif "--no-cnv" in out:
        flags["no_cnv"] = "--no-cnv"
    elif "-no-cnv" in out:
        flags["no_cnv"] = "-no-cnv"
    else:
        flags["no_cnv"] = None

    # simple-io spelling
    if "--simple-io" in out:
        flags["simple_io"] = "--simple-io"
    else:
        flags["simple_io"] = None

    # no-display-prompt spelling
    if "--no-display-prompt" in out:
        flags["no_display_prompt"] = "--no-display-prompt"
    elif "-no-display-prompt" in out:
        flags["no_display_prompt"] = "-no-display-prompt"
    else:
        flags["no_display_prompt"] = None

    _LLAMA_FLAGS = flags
    return flags


class SysStats:
    def __init__(self):
        self._last_cpu = None
        if psutil:
            try:
                psutil.cpu_percent(None)
            except Exception:
                pass

    def cpu(self) -> float:
        if psutil:
            try:
                return float(psutil.cpu_percent(None))
            except Exception:
                pass
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()[1:]
            vals = list(map(int, parts))
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            if self._last_cpu:
                di = idle - self._last_cpu[0]
                dt = total - self._last_cpu[1]
                self._last_cpu = (idle, total)
                return 100.0 * (1 - di / dt) if dt > 0 else 0.0
            self._last_cpu = (idle, total)
            return 0.0
        except Exception:
            pass
        try:
            load = os.getloadavg()[0]
            return min(100.0, 100.0 * load / (os.cpu_count() or 1))
        except Exception:
            return 0.0

    def mem(self):
        if psutil:
            try:
                m = psutil.virtual_memory()
                return m.total - m.available, m.total
            except Exception:
                pass
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0]) * 1024
            total = info["MemTotal"]
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            return total - avail, total
        except Exception:
            return 0, 0


# ───────────────────────── modal base ─────────────────────────
class BaseModal(ModalScreen):
    """Common chrome for all modals."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
    ]

    DEFAULT_CSS = """
    BaseModal {
        align: center middle;
        background: rgba(17, 17, 27, 0.85);
    }
    BaseModal > Vertical {
        background: #1e1e2e;
        border: round #89b4fa;
        border-title-color: #f38ba8;
        border-title-style: bold;
        padding: 1 2;
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 85%;
    }
    BaseModal .modal-hint {
        color: #6c7086;
        text-style: italic;
        padding: 1 0 0 0;
    }
    BaseModal .modal-section {
        color: #f9e2af;
        text-style: bold;
        padding: 1 0 0 0;
    }
    BaseModal ListView {
        height: 1fr;
        border: round #313244;
        background: #11111b;
    }
    BaseModal ListItem {
        padding: 0 1;
    }
    BaseModal ListItem.--highlight {
        background: #313244;
    }
    BaseModal Button {
        margin: 0 1 0 0;
    }
    """

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def toast(self, msg: str) -> None:
        app = self.app
        if hasattr(app, "log_line"):
            app.log_line(msg)


# ───────────────────────── help panel ─────────────────────────
class HelpScreen(BaseModal):
    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "help"
            yield Static(self._build_help(), markup=True)
            yield Static("Esc / q to close", classes="modal-hint")

    def _build_help(self) -> str:
        return (
            "[bold #f38ba8]llama-tui2 — keys[/]\n\n"
            "[#89b4fa]Enter[/]      send message\n"
            "[#89b4fa]Ctrl+X[/]     stop generation\n"
            "[#89b4fa]Ctrl+L[/]     clear screen\n"
            "[#89b4fa]Ctrl+R[/]     reset conversation\n"
            "[#89b4fa]Ctrl+N[/]     new session\n"
            "[#89b4fa]Ctrl+S[/]     save session\n"
            "[#89b4fa]Ctrl+Q[/]     quit\n\n"
            "[bold #f38ba8]panels[/]\n\n"
            "[#a6e3a1]F1[/]  help        this screen\n"
            "[#a6e3a1]F2[/]  model       switch model / details\n"
            "[#a6e3a1]F3[/]  settings    generation settings\n"
            "[#a6e3a1]F4[/]  stats       performance history\n"
            "[#a6e3a1]F5[/]  sessions    saved conversations\n"
            "[#a6e3a1]F6[/]  system      system prompt editor\n"
            "[#a6e3a1]F7[/]  browser     CDP & HAR monitor\n"
            "[#a6e3a1]F8[/]  cron        schedule maps scrapes\n\n"
            "[bold #f38ba8]commands[/]\n\n"
            "[bold #89b4fa]/agent <goal>[/]          autonomous multi-tab CDP agent (AX/CSS/JEV/HAR)\n"
            "[bold #89b4fa]/fetch <url>[/]           fetch page via CDP or HTTP and inject to chat\n"
            "[bold #89b4fa]/click <target>[/]        click element by index or CSS selector\n"
            "[bold #89b4fa]/type <sel> <text>[/]      type text into input field\n"
            "[bold #89b4fa]/har [start|stop|save][/]  control background network traffic capture\n"
            "[bold #89b4fa]/cdp [port][/]             connect/probe Chrome CDP (9222/9226/9228)\n"
            "[bold #89b4fa]/cron[/]                   open cron job menu (same as F8)\n"
            "[bold #89b4fa]/print <path>[/]            show a local file in chat (jsonl pretty)\n"
            "[bold #89b4fa]/runlog[/]                  show latest agent_runs/run_*.jsonl\n"
            "[bold #89b4fa]/help, /model, /clear, /reset, /stop[/]\n\n"
            "[dim]Tip: plain text like “phone numbers of jewellers in pune”\n"
            "auto-routes to /agent → skills (decision + pincode CSV + maps).\n"
            "Live when Chrome CDP is up; say “dry” to force plan-only.\n"
            "Say “daily” / “hourly” for cron hints → add via F8.[/]"
        )


# ───────────────────────── model picker ─────────────────────────
class ModelScreen(BaseModal):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("r", "rescan", "Rescan"),
        Binding("enter", "switch_model", "Use"),
        Binding("t", "toggle_tiny", "Toggle tiny"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "models"
            yield Static(
                "[#89b4fa]Enter[/] use   [#a6e3a1]r[/] rescan   "
                "[#a6e3a1]t[/] toggle tiny   [#6c7086]● = active[/]",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="model-list")
            yield Static(id="model-details", markup=True)
            yield Static("Esc / q to close", classes="modal-hint")

    def on_mount(self) -> None:
        self._include_tiny = False
        self._refresh_list()
        self.query_one("#model-list", ListView).focus()
        self._update_details()

    def _refresh_list(self) -> None:
        lv = self.query_one("#model-list", ListView)
        lv.clear()
        models = discover_models(include_tiny=getattr(self, "_include_tiny", False))
        active = ModelState.path
        if not models:
            msg = (
                "[#f38ba8](no .gguf found — set LLAMA_MODEL_DIR or press t)[/]"
                if not getattr(self, "_include_tiny", False)
                else "[#f38ba8](no .gguf found anywhere)[/]"
            )
            lv.append(ListItem(Label(msg)))
            return
        active_real = os.path.realpath(active) if active else ""
        for path in models:
            is_active = os.path.realpath(path) == active_real
            mark = "[#a6e3a1]●[/]" if is_active else " "
            try:
                size = fmt_bytes(os.path.getsize(path))
            except OSError:
                size = "—"
            tiny_tag = "[#f38ba8] tiny[/]" if is_probably_vocab(path) else ""
            label = Label(
                f"{mark} {os.path.basename(path)}  "
                f"[#6c7086]{size}  {quant_of(path)}[/]{tiny_tag}"
            )
            lv.append(ListItem(label))

    def _selected_path(self):
        lv = self.query_one("#model-list", ListView)
        if lv.index is None or lv.index < 0:
            return None
        models = discover_models(include_tiny=getattr(self, "_include_tiny", False))
        if lv.index >= len(models):
            return None
        return models[lv.index]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._update_details()

    def _update_details(self) -> None:
        path = self._selected_path()
        try:
            box = self.query_one("#model-details", Static)
        except Exception:
            return
        if not path:
            box.update("[#6c7086]no selection[/]")
            return
        exists = os.path.exists(path)
        try:
            size = fmt_bytes(os.path.getsize(path)) if exists else "—"
        except OSError:
            size = "—"
        status = "[#a6e3a1]✓[/]" if exists else "[#f38ba8]✗[/]"
        warn = ""
        if is_probably_vocab(path):
            warn = "   [#f38ba8]⚠ vocab-only or tiny — likely won't generate[/]"
        box.update(
            f"[bold #89b4fa]path[/]   {path}\n"
            f"[bold #89b4fa]size[/]   {size}   "
            f"[bold #89b4fa]quant[/]  {quant_of(path)}   "
            f"[bold #89b4fa]file[/]   {status}{warn}"
        )

    def action_rescan(self) -> None:
        self._refresh_list()
        self._update_details()
        self.toast("model list rescanned")

    def action_toggle_tiny(self) -> None:
        self._include_tiny = not getattr(self, "_include_tiny", False)
        self._refresh_list()
        self._update_details()
        state = "on" if self._include_tiny else "off"
        self.toast(f"show tiny/vocab files: {state}")

    def action_switch_model(self) -> None:
        path = self._selected_path()
        if not path or not os.path.exists(path):
            return
        if ModelState.path and os.path.realpath(path) == os.path.realpath(ModelState.path):
            self.dismiss(None)
            return
        try:
            self.app._apply_model_switch(path)
        except Exception as e:
            self.toast(f"[#f38ba8]switch failed:[/] {e}")
            return
        self.dismiss(None)


# ───────────────────────── settings panel ─────────────────────────
class SettingsScreen(BaseModal):
    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "settings"
            yield Static("[bold #f9e2af]generation[/]", classes="modal-section")
            yield Static(self._body(), markup=True, id="settings-body")
            with Horizontal():
                yield Button("threads -", id="thr-dec")
                yield Button("threads +", id="thr-inc")
                yield Button("temp -", id="tmp-dec")
                yield Button("temp +", id="tmp-inc")
            yield Static(
                "Changes apply to the next message. Esc to close.",
                classes="modal-hint",
            )

    def _body(self) -> str:
        return (
            f"threads   {THREADS}   (1–{os.cpu_count() or 8})\n"
            f"ctx       {CTX}\n"
            f"n_predict {N_PREDICT}\n"
            f"temp      {TEMP}\n"
            f"top_p     {TOP_P}\n"
            f"repeat    {REPEAT_PENALTY}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        global THREADS, TEMP
        if event.button.id == "thr-inc":
            THREADS = min(THREADS + 1, os.cpu_count() or 8)
        elif event.button.id == "thr-dec":
            THREADS = max(1, THREADS - 1)
        elif event.button.id == "tmp-inc":
            TEMP = round(min(TEMP + 0.1, 1.5), 2)
        elif event.button.id == "tmp-dec":
            TEMP = round(max(TEMP - 0.1, 0.0), 2)
        else:
            return
        self.query_one("#settings-body", Static).update(self._body())
        self.toast(f"settings updated (threads={THREADS}, temp={TEMP})")


# ───────────────────────── stats panel ─────────────────────────
class StatsScreen(BaseModal):
    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "stats"
            yield Static(id="stats-body", markup=True)
            yield Static("Esc / q to close", classes="modal-hint")

    def on_mount(self) -> None:
        self._refresh()
        self._timer = self.set_interval(1.0, self._refresh)

    def on_unmount(self) -> None:
        timer = getattr(self, "_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass

    def _refresh(self) -> None:
        app = self.app
        hist = list(app.tps_hist)
        recent = [h for h in hist[-10:] if h > 0]
        avg = sum(recent) / len(recent) if recent else 0.0
        peak = max(hist) if hist else 0.0
        up = int(time.time() - app.started)
        body = (
            f"[bold #f9e2af]this turn[/]\n"
            f"gen t/s     {app.last['tps']:6.1f}\n"
            f"prompt t/s  {app.last['ptps']:6.1f}\n"
            f"tokens out  {app.last['gtok']}\n"
            f"tokens in   {app.last['ptok']}\n"
            f"elapsed     {app.last['total']:.2f}s\n\n"
            f"[bold #f9e2af]session[/]\n"
            f"turns       {app.turns}\n"
            f"total out   {app.total_gen_tokens}\n"
            f"avg t/s     {avg:6.2f}  (last {len(recent)})\n"
            f"peak t/s    {peak:6.2f}\n\n"
            f"[bold #f9e2af]runtime[/]\n"
            f"uptime      {up // 60:02d}:{up % 60:02d}\n"
            f"state       {app.state}\n"
        )
        try:
            self.query_one("#stats-body", Static).update(body)
        except Exception:
            pass


# ───────────────────────── sessions panel ─────────────────────────
class SessionScreen(BaseModal):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("d", "delete_session", "Delete"),
        Binding("s", "save_current", "Save"),
        Binding("enter", "load_session", "Load"),
    ]

    def compose(self) -> ComposeResult:
        os.makedirs(SESS_DIR, exist_ok=True)
        with Vertical() as v:
            v.border_title = "sessions"
            yield Static(
                "[#89b4fa]Enter[/] load   [#f38ba8]d[/] delete   "
                "[#a6e3a1]s[/] save current",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="sess-list")
            yield Static("Esc / q to close", classes="modal-hint")

    def on_mount(self) -> None:
        lv = self.query_one("#sess-list", ListView)
        files = sorted(
            (f for f in os.listdir(SESS_DIR) if f.endswith(".json")),
            key=lambda f: os.path.getmtime(os.path.join(SESS_DIR, f)),
            reverse=True,
        )
        if not files:
            lv.append(ListItem(Label("[#6c7086](no saved sessions)[/]")))
            return
        for f in files:
            ts = time.strftime(
                "%Y-%m-%d %H:%M",
                time.localtime(os.path.getmtime(os.path.join(SESS_DIR, f))),
            )
            lv.append(ListItem(Label(f"{f[:-5]}  [#6c7086]{ts}[/]")))

    def _selected_file(self):
        lv = self.query_one("#sess-list", ListView)
        if lv.index is None or lv.index < 0:
            return None
        try:
            item = lv.children[lv.index]
        except IndexError:
            return None
        label = item.query_one(Label)
        try:
            text = str(label.renderable)
        except Exception:
            text = str(label.render())
        text = re.sub(r"\[.*?\]", "", text).strip()
        if text.startswith("("):
            return None
        name = text.split("  ")[0].strip()
        return os.path.join(SESS_DIR, name + ".json")

    def action_load_session(self) -> None:
        path = self._selected_file()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.app.history = [tuple(x) for x in data.get("history", [])]
            self.app.turns = data.get("turns", len(self.app.history) // 2)
            chat = self.app.query_one("#chat", VerticalScroll)
            for child in list(chat.children):
                child.remove()
            for role, text in self.app.history:
                self.app.add_message("user" if role == "user" else "ai", text)
            self.toast(f"loaded session {os.path.basename(path)}")
            self.dismiss(None)
        except Exception as e:
            self.toast(f"[#f38ba8]load failed:[/] {e}")

    def action_save_current(self) -> None:
        os.makedirs(SESS_DIR, exist_ok=True)
        name = time.strftime("session-%Y%m%d-%H%M%S")
        path = os.path.join(SESS_DIR, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"history": self.app.history, "turns": self.app.turns},
                f,
                indent=2,
            )
        self.toast(f"saved {name}")
        self.dismiss(None)

    def action_delete_session(self) -> None:
        path = self._selected_file()
        if not path or not os.path.exists(path):
            return
        try:
            os.unlink(path)
            self.toast(f"deleted {os.path.basename(path)}")
            self.dismiss(None)
            self.app.push_screen(SessionScreen())
        except Exception as e:
            self.toast(f"[#f38ba8]delete failed:[/] {e}")


# ───────────────────────── system prompt panel ─────────────────────────
class SystemScreen(BaseModal):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("ctrl+s", "save_system", "Save"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "system prompt"
            if HAS_TEXTAREA:
                yield TextArea(SYSTEM_PROMPT, id="sys-editor", language=None)
            else:
                yield Static(SYSTEM_PROMPT, id="sys-editor")
            with Horizontal():
                yield Button("save", id="sys-save", variant="success")
                yield Button("reset default", id="sys-reset", variant="warning")
            yield Static("Ctrl+S save · Esc close", classes="modal-hint")

    def action_save_system(self) -> None:
        global SYSTEM_PROMPT
        if HAS_TEXTAREA:
            try:
                SYSTEM_PROMPT = self.query_one("#sys-editor", TextArea).text
            except Exception:
                return
        self.toast("system prompt updated (applies next message)")
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        global SYSTEM_PROMPT
        if event.button.id == "sys-save":
            self.action_save_system()
        elif event.button.id == "sys-reset":
            SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT
            if HAS_TEXTAREA:
                try:
                    self.query_one("#sys-editor", TextArea).text = SYSTEM_PROMPT
                except Exception:
                    pass
            self.toast("system prompt reset to default")


# ───────────────────────── browser & har panel ─────────────────────────
class BrowserScreen(BaseModal):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("r", "refresh_info", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "browser & har network monitor"
            yield Static(self._build_info(), id="browser-info", markup=True)
            with Horizontal():
                yield Button("probe cdp", id="btn-cdp-connect", variant="success")
                yield Button("toggle har", id="btn-har-toggle", variant="primary")
                yield Button("save har", id="btn-har-save", variant="warning")
            yield Static("Esc / q to close · r to refresh", classes="modal-hint")

    def _build_info(self) -> str:
        app = self.app
        cdp_stat = "[bold #a6e3a1]CONNECTED[/]" if app.fetcher.is_connected() else "[bold #6c7086]OFFLINE[/]"
        har_stat = app.har.get_summary()
        har_rec = "[bold #f9e2af]RECORDING[/]" if har_stat["is_capturing"] else "[bold #6c7086]IDLE[/]"

        domains_str = ", ".join(har_stat["domains"]) if har_stat["domains"] else "(none)"
        return (
            f"[bold #89b4fa]Chrome DevTools Protocol (CDP)[/]\n"
            f"Status: {cdp_stat}  Debug Port: {app.fetcher.port}\n"
            f"Active Tab: [bold]{app.fetcher.active_title or '(none)'}[/]\n"
            f"URL: {app.fetcher.active_url or '(none)'}\n\n"
            f"[bold #89b4fa]HAR Network Traffic Recorder[/]\n"
            f"Status: {har_rec}  Duration: {har_stat['duration_seconds']}s\n"
            f"Recorded Requests: {har_stat['total_requests']}  (APIs: {har_stat['api_requests']})\n"
            f"Domains: {domains_str}\n\n"
            f"[bold #f9e2af]Quick Commands:[/] /fetch <url> · /agent <goal> · /har [start|stop|save]"
        )

    def action_refresh_info(self) -> None:
        self.query_one("#browser-info", Static).update(self._build_info())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.app
        if event.button.id == "btn-cdp-connect":
            app.handle_cdp_cmd("")
        elif event.button.id == "btn-har-toggle":
            if app.har.is_capturing:
                app.handle_har_cmd("stop")
            else:
                app.handle_har_cmd("start")
        elif event.button.id == "btn-har-save":
            app.handle_har_cmd("save")
        self.query_one("#browser-info", Static).update(self._build_info())


# ───────────────────────── cron / maps_scrape scheduler ─────────────────────────
class CronScreen(BaseModal):
    """F8 menu: schedule daily/hourly maps_scrape jobs into agent.db."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("r", "refresh_jobs", "Refresh"),
        Binding("a", "add_job", "Add"),
        Binding("t", "toggle_job", "Toggle"),
        Binding("d", "delete_job", "Delete"),
    ]

    DEFAULT_CSS = """
    CronScreen > Vertical {
        width: 88%;
        max-width: 100;
        height: 85%;
    }
    CronScreen #cron-list {
        height: 12;
        border: round #313244;
        background: #11111b;
    }
    CronScreen Input {
        margin: 0 0 1 0;
        border: round #313244;
        background: #11111b;
    }
    CronScreen Input:focus {
        border: round #89b4fa;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "cron · maps scrapes"
            yield Static(
                "[#89b4fa]a[/] add   [#f9e2af]t[/] toggle   [#f38ba8]d[/] delete   "
                "[#a6e3a1]r[/] refresh   presets fill schedule",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="cron-list")
            yield Static("[bold #f9e2af]new job[/]", classes="modal-section")
            yield Input(placeholder="name  e.g. jewellers-pune-daily", id="cron-name")
            yield Input(
                placeholder="goal  e.g. daily scrape jewellers phones in Pune",
                id="cron-goal",
            )
            yield Input(value="0 9 * * *", placeholder="cron expr or daily/hourly", id="cron-expr")
            with Horizontal():
                yield Button("daily 09:00", id="preset-daily")
                yield Button("hourly", id="preset-hourly")
                yield Button("night 21:00", id="preset-night")
                yield Button("weekdays", id="preset-weekdays")
            with Horizontal():
                yield Button("add job", id="btn-cron-add", variant="success")
                yield Button("toggle", id="btn-cron-toggle", variant="primary")
                yield Button("delete", id="btn-cron-del", variant="error")
                yield Button("dry-run on add", id="btn-cron-dry", variant="warning")
            yield Static(id="cron-status", markup=True)
            yield Static(
                "Jobs run as task_type=maps_scrape (skills: decision→pincodes→maps_geo). "
                "Esc / q to close.",
                classes="modal-hint",
            )

    def on_mount(self) -> None:
        self._dry_run = False
        self._jobs: list[dict] = []
        self._prefill_from_hint()
        self.action_refresh_jobs()

    def _store(self) -> CronStore:
        app = self.app
        if not getattr(app, "cron", None):
            app.cron = CronStore()
        return app.cron

    def _prefill_from_hint(self) -> None:
        """If last agent run suggested a cron, seed the form."""
        agent = getattr(self.app, "agent", None)
        if not agent or not getattr(agent, "extracted", None):
            return
        # suggested_cron lives on finished notify / memory; also check decision
        # Prefer goal text from chat tip if present in memory tasks
        try:
            mem = getattr(agent, "memory", None)
            if not mem:
                return
            tasks = mem.list_tasks() if hasattr(mem, "list_tasks") else []
            cron_task = next((t for t in tasks if t.get("name") == "cron"), None)
            if not cron_task:
                return
            arts = cron_task.get("artifacts") or {}
            if isinstance(arts, str):
                arts = json.loads(arts)
            expr = arts.get("cron_expr") or ""
            goal = arts.get("goal") or cron_task.get("goal") or ""
            if expr:
                self.query_one("#cron-expr", Input).value = expr
            if goal:
                self.query_one("#cron-goal", Input).value = goal
                slug = re.sub(r"[^a-z0-9]+", "-", goal.lower())[:40].strip("-")
                self.query_one("#cron-name", Input).value = slug or "maps-daily"
        except Exception:
            pass

    def action_refresh_jobs(self) -> None:
        store = self._store()
        self._jobs = store.list_jobs()
        lv = self.query_one("#cron-list", ListView)
        lv.clear()
        if not self._jobs:
            lv.append(ListItem(Label("[#6c7086](no jobs — fill form + add)[/]")))
        else:
            for j in self._jobs:
                en = "[#a6e3a1]ON [/]" if j.get("enabled") else "[#6c7086]OFF[/]"
                dry = " dry" if (j.get("payload") or {}).get("dry_run") else ""
                goal = (j.get("goal") or "")[:48]
                label = (
                    f"{en} [bold]{j.get('name')}[/]  "
                    f"[#89b4fa]{j.get('cron_expr')}[/]{dry}  "
                    f"[#6c7086]{goal}[/]"
                )
                lv.append(ListItem(Label(label)))
        dry_lbl = "dry-run ON" if self._dry_run else "dry-run off"
        self.query_one("#cron-status", Static).update(
            f"[#6c7086]{len(self._jobs)} job(s) · new jobs: {dry_lbl} · "
            f"task_type={CronStore.TASK_TYPE}[/]"
        )

    def _selected_name(self) -> str | None:
        lv = self.query_one("#cron-list", ListView)
        if lv.index is None or lv.index < 0 or not self._jobs:
            return None
        if lv.index >= len(self._jobs):
            return None
        return self._jobs[lv.index].get("name")

    def _resolve_expr(self, raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return "0 9 * * *"
        low = raw.lower()
        for label, expr in CronStore.PRESETS:
            if low == label or low == label.replace(" ", ""):
                return expr
        # natural words
        aliases = {
            "daily": "0 9 * * *",
            "every day": "0 9 * * *",
            "hourly": "0 * * * *",
            "every hour": "0 * * * *",
            "night": "0 21 * * *",
            "every night": "0 21 * * *",
            "weekdays": "0 9 * * 1-5",
            "weekly": "0 9 * * 1",
            "every minute": "* * * * *",
        }
        if low in aliases:
            return aliases[low]
        return raw

    def action_add_job(self) -> None:
        name = self.query_one("#cron-name", Input).value.strip()
        goal = self.query_one("#cron-goal", Input).value.strip()
        expr = self._resolve_expr(self.query_one("#cron-expr", Input).value)
        if not name or not goal:
            self.query_one("#cron-status", Static).update(
                "[#f38ba8]name and goal required[/]"
            )
            return
        try:
            job = self._store().add_job(name, expr, goal, dry_run=self._dry_run)
            self.toast(
                f"cron added: {job['name']} → {job['cron_expr']} "
                f"(next {job['next_run_at'][:19]})"
            )
            self.action_refresh_jobs()
        except Exception as e:
            self.query_one("#cron-status", Static).update(f"[#f38ba8]add failed: {e}[/]")

    def action_toggle_job(self) -> None:
        name = self._selected_name()
        if not name:
            self.query_one("#cron-status", Static).update(
                "[#f9e2af]select a job in the list first[/]"
            )
            return
        job = next((j for j in self._jobs if j.get("name") == name), None)
        enabled = not bool(job.get("enabled")) if job else True
        self._store().enable(name, enabled)
        self.toast(f"{name}: {'enabled' if enabled else 'disabled'}")
        self.action_refresh_jobs()

    def action_delete_job(self) -> None:
        name = self._selected_name()
        if not name:
            self.query_one("#cron-status", Static).update(
                "[#f9e2af]select a job in the list first[/]"
            )
            return
        self._store().delete(name)
        self.toast(f"deleted {name}")
        self.action_refresh_jobs()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        presets = {
            "preset-daily": "0 9 * * *",
            "preset-hourly": "0 * * * *",
            "preset-night": "0 21 * * *",
            "preset-weekdays": "0 9 * * 1-5",
        }
        if bid in presets:
            self.query_one("#cron-expr", Input).value = presets[bid]
            return
        if bid == "btn-cron-add":
            self.action_add_job()
        elif bid == "btn-cron-toggle":
            self.action_toggle_job()
        elif bid == "btn-cron-del":
            self.action_delete_job()
        elif bid == "btn-cron-dry":
            self._dry_run = not self._dry_run
            btn = event.button
            btn.label = "dry-run ON" if self._dry_run else "dry-run on add"
            self.action_refresh_jobs()


# ───────────────────────── app ─────────────────────────
class LlamaTUI(App):
    TITLE = "llama-tui"

    CSS = f"""
    Screen {{
        background: #11111b;
        color: {C_TEXT};
    }}
    #topbar {{
        dock: top;
        height: 1;
        background: #181825;
        color: {C_TEXT};
        padding: 0 1;
    }}
    #statusbar {{
        height: 1;
        background: #181825;
        color: {C_DIM};
        padding: 0 1;
    }}
    #taskbar {{
        height: 4;
        background: #1e1e2e;
        color: {C_TEXT};
        padding: 0 1;
        border-top: solid #89b4fa;
        border-bottom: solid #313244;
    }}
    #taskbar.idle {{
        color: #6c7086;
        border-top: solid #313244;
    }}
    #taskbar.active {{
        border-top: solid #a6e3a1;
    }}
    #taskbar.caution {{
        border-top: solid #f9e2af;
        background: #2a2418;
    }}
    .box {{
        border: round {C_BORDER};
        border-title-color: {C_TITLE};
        border-title-style: bold;
        border-subtitle-color: {C_DIM};
        background: #11111b;
        padding: 0 1;
    }}
    #left {{ width: 2fr; }}
    #right {{ width: 1fr; min-width: 30; }}
    #chat {{ height: 1fr; }}
    #input {{
        height: 3;
        border: round {C_USER};
        border-title-color: {C_USER};
        background: #11111b;
    }}
    #input:focus {{ border: round {C_AI}; }}
    #cpu {{ height: 8; }}
    #mem {{ height: 5; }}
    #perf {{ height: 9; }}
    #browser {{ height: 7; }}
    #log {{ height: 1fr; }}
    .msg {{ margin-bottom: 1; }}
    Footer {{ background: #181825; color: {C_DIM}; }}
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+x", "stop", "Stop"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+r", "reset", "Reset ctx"),
        Binding("ctrl+n", "new_session", "New"),
        Binding("ctrl+s", "save_session", "Save"),
        Binding("f1", "panel_help", "Help"),
        Binding("f2", "panel_model", "Model"),
        Binding("f3", "panel_settings", "Settings"),
        Binding("f4", "panel_stats", "Stats"),
        Binding("f5", "panel_sessions", "Sessions"),
        Binding("f6", "panel_system", "System"),
        Binding("f7", "panel_browser", "Browser"),
        Binding("f8", "panel_cron", "Cron"),
    ]

    # ── layout ──
    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal():
            with Vertical(id="left"):
                chat = VerticalScroll(id="chat", classes="box")
                chat.border_title = "chat"
                yield chat
                yield Static(id="taskbar", classes="idle")
                yield Static(id="statusbar")
                inp = Input(
                    placeholder="type a message, Enter to send…  (/help · /agent <goal> · /fetch <url>)",
                    id="input",
                )
                inp.border_title = "input"
                yield inp
            with Vertical(id="right"):
                yield Static(id="cpu", classes="box")
                yield Static(id="mem", classes="box")
                yield Static(id="perf", classes="box")
                yield Static(id="browser", classes="box")
                yield RichLog(id="log", classes="box", markup=True, wrap=True, max_lines=300)
        yield Footer()

    # ── lifecycle ──
    def on_mount(self) -> None:
        self.fetcher = PageFetcher()
        self.har = HarManager()
        self.cron = CronStore()
        self.agent = None
        self.sys = SysStats()
        self.cpu_hist = deque(maxlen=200)
        self.tps_hist = deque(maxlen=200)
        self.history = []
        self.busy = False
        self.proc = None
        self.stop_flag = False
        self.started = time.time()
        self.state = "idle"
        self.gen_tokens = 0
        self.gen_start = 0.0
        self.last = {"tps": 0.0, "ptps": 0.0, "ptok": 0, "gtok": 0, "total": 0.0}
        self.total_gen_tokens = 0
        self.turns = 0
        self.proc_rss = 0
        self.live_widget = None
        self.task_progress: dict = {
            "active": False,
            "label": "",
            "step": 0,
            "total": 0,
            "phase": "",
            "cards": 0,
            "phones": 0,
            "caution": "",
            "tasks": [],
            "overlap": None,
            "novelty": None,
        }
        self._render_taskbar()

        self.query_one("#cpu").border_title = "cpu"
        self.query_one("#mem").border_title = "mem"
        self.query_one("#perf").border_title = "llama"
        self.query_one("#browser").border_title = "browser & har"
        self.query_one("#log").border_title = "log"

        # Probe CDP port
        found_port = self.fetcher.find_available_port()
        if found_port and self.fetcher.connect(found_port):
            self.log_line(f"[#a6e3a1]CDP connected:[/] port {found_port} ({self.fetcher.active_title})")
        else:
            self.log_line("[#6c7086]CDP offline (use /cdp to connect or /fetch for HTTP)[/]")

        self.log_line(f"model: [b]{os.path.basename(ModelState.path)}[/b]")
        if not os.path.exists(LLAMA_BIN):
            self.log_line(f"[{C_ERR}]llama-cli not found:[/] {LLAMA_BIN}")
        elif not os.access(LLAMA_BIN, os.X_OK):
            self.log_line(f"[{C_ERR}]llama-cli not executable:[/] {LLAMA_BIN}")
        if not os.path.exists(ModelState.path):
            self.log_line(f"[{C_ERR}]model not found:[/] {ModelState.path}")
        elif is_probably_vocab(ModelState.path):
            self.log_line(
                f"[{C_ERR}]model looks like vocab-only/tiny file — switch with F2[/]"
            )
        # Probe llama-cli flags once, and log the detected spelling.
        flags = llama_flags()
        self.log_line(
            f"flags: no_cnv={flags['no_cnv'] or '(none)'} "
            f"no_display_prompt={flags['no_display_prompt'] or '(none)'}"
        )
        if not psutil:
            self.log_line(f"[{C_DIM}]psutil missing — using /proc fallbacks[/]")
        if not HAS_TEXTAREA:
            self.log_line(f"[{C_DIM}]TextArea unavailable — system prompt read-only[/]")

        self.add_message(
            "sys",
            f"Welcome. Model: {os.path.basename(ModelState.path)}. "
            "Type below and press Enter. F1 help · F2 switch model.",
        )
        self.set_interval(1.0, self.refresh_panels)
        self.refresh_panels()
        self.query_one("#input").focus()

    # ── small UI utils ──
    def log_line(self, markup: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        try:
            self.query_one("#log", RichLog).write(f"[{C_DIM}]{stamp}[/] {markup}")
        except Exception:
            pass

    def set_task_progress(self, **kwargs) -> None:
        """Update agent/maps task progress bar (call from UI thread)."""
        tp = self.task_progress
        for k, v in kwargs.items():
            if k in tp or k in ("active", "label", "step", "total", "phase",
                                "cards", "phones", "caution", "tasks", "overlap", "novelty"):
                tp[k] = v
        if "active" not in kwargs:
            tp["active"] = True
        self._render_taskbar()

    def clear_task_progress(self) -> None:
        self.task_progress = {
            "active": False,
            "label": "",
            "step": 0,
            "total": 0,
            "phase": "",
            "cards": 0,
            "phones": 0,
            "caution": "",
            "tasks": [],
            "overlap": None,
            "novelty": None,
        }
        self._render_taskbar()

    def _render_taskbar(self) -> None:
        """Clear, always-visible task progress strip above the status bar."""
        tp = getattr(self, "task_progress", None) or {}
        try:
            bar = self.query_one("#taskbar", Static)
        except Exception:
            return

        t = Text()
        if not tp.get("active"):
            t.append(" TASK ", style="bold #11111b on #45475a")
            t.append("  idle — /agent <goal> to start", style=C_DIM)
            bar.set_classes("idle")
            bar.update(t)
            return

        step = int(tp.get("step") or 0)
        total = int(tp.get("total") or 0)
        pct = (100.0 * step / total) if total > 0 else (100.0 if tp.get("phase") == "done" else 0.0)
        caution = (tp.get("caution") or "").strip()
        label = (tp.get("label") or "agent").strip()
        phase = (tp.get("phase") or "").strip()

        if caution:
            bar.set_classes("caution")
            hdr_style = "bold #11111b on #f9e2af"
            hdr = " CAUTION "
        else:
            bar.set_classes("active")
            hdr_style = "bold #11111b on #a6e3a1"
            hdr = " TASK "

        # line 1: label + meter + step/total
        t.append(hdr, style=hdr_style)
        t.append(f" {label}", style=f"bold {C_TEXT}")
        if phase:
            t.append(f"  · {phase}", style=C_USER)
        t.append("\n  ")
        # Prefer chat column width for a readable bar
        try:
            width = max(16, min(36, self.query_one("#left").size.width - 28))
        except Exception:
            width = 24
        t.append_text(meter(pct, width))
        if total > 0:
            t.append(f"  {step}/{total}", style=f"bold {C_AI}")
            t.append(f" ({pct:.0f}%)", style=C_DIM)
        else:
            t.append(f"  {pct:.0f}%", style=C_DIM)

        cards = int(tp.get("cards") or 0)
        phones = int(tp.get("phones") or 0)
        if cards or phones:
            t.append(f"  cards={cards}", style=C_TEXT)
            t.append(f" phones={phones}", style="#a6e3a1" if phones else C_DIM)

        novelty = tp.get("novelty")
        overlap = tp.get("overlap")
        if novelty is not None:
            t.append(f"  new={float(novelty)*100:.0f}%", style=C_DIM)
        if overlap is not None:
            t.append(f"  overlap={float(overlap)*100:.0f}%", style=C_WARN if float(overlap) >= 0.9 else C_DIM)

        if caution:
            t.append(f"\n  ⚠ {caution[:90]}", style=f"bold {C_WARN}")

        bar.update(t)

    def add_message(self, role: str, text: str) -> Static:
        chat = self.query_one("#chat", VerticalScroll)
        w = Static(self._render_msg(role, text), classes="msg")
        chat.mount(w)
        chat.scroll_end(animate=False)
        return w

    @staticmethod
    def _render_msg(role: str, text: str, cursor: bool = False) -> Text:
        t = Text()
        if role == "user":
            t.append("▌you  ", style=f"bold {C_USER}")
            t.append(text, style=C_TEXT)
        elif role == "ai":
            t.append("▌ai   ", style=f"bold {C_AI}")
            t.append(text, style=C_TEXT)
            if cursor:
                t.append("█", style=C_AI)
        else:
            t.append(text, style=f"italic {C_DIM}")
        return t

    # ── periodic panels ──
    def refresh_panels(self) -> None:
        width = max(10, self.query_one("#right").size.width - 6)

        up = int(time.time() - self.started)
        state_style = {"idle": C_AI, "generating": C_WARN, "loading": C_WARN}.get(
            self.state, C_TEXT
        )

        active = ModelState.path
        warn = ""
        try:
            if not os.path.exists(active):
                warn = "  ⚠ missing"
            elif is_probably_vocab(active):
                warn = "  ⚠ tiny"
        except Exception:
            pass

        bar = Text()
        bar.append(" llama-tui ", style=f"bold #11111b on {C_TITLE}")
        bar.append(f"  {os.path.basename(active) if active else '?'}{warn}", style=C_TEXT)
        bar.append("   state: ", style=C_DIM)
        bar.append(self.state, style=f"bold {state_style}")
        bar.append(f"   up {up // 60:02d}:{up % 60:02d}", style=C_DIM)
        bar.append(f"   {time.strftime('%H:%M:%S')}", style=C_TEXT)
        self.query_one("#topbar", Static).update(bar)

        cpu = self.sys.cpu()
        self.cpu_hist.append(cpu)
        t = Text()
        t.append(f"total {cpu:5.1f}%\n", style=f"bold {gradient(cpu / 100)}")
        t.append_text(meter(cpu, width))
        t.append("\n")
        for _ in range(2):
            t.append_text(sparkline(self.cpu_hist, width))
            t.append("\n")
        t.append(f"threads {THREADS}/{os.cpu_count() or '?'}", style=C_DIM)
        self.query_one("#cpu", Static).update(t)

        used, total = self.sys.mem()
        pct = 100.0 * used / total if total else 0.0
        t = Text()
        t.append(f"used {fmt_bytes(used)} / {fmt_bytes(total)}  ", style=C_TEXT)
        t.append(f"{pct:.0f}%\n", style=f"bold {gradient(pct / 100)}")
        t.append_text(meter(pct, width))
        if self.proc_rss:
            t.append(f"\nllama-cli rss {fmt_bytes(self.proc_rss)}", style=C_DIM)
        self.query_one("#mem", Static).update(t)

        if self.busy and self.gen_start:
            live = self.gen_tokens / max(time.time() - self.gen_start, 1e-6)
        else:
            live = 0.0
        self.tps_hist.append(live)
        t = Text()
        t.append("gen    ", style=C_DIM)
        t.append(f"{self.last['tps']:6.1f} t/s", style=f"bold {C_AI}")
        t.append(f"  ({self.last['gtok']} tok)\n", style=C_DIM)
        t.append("prompt ", style=C_DIM)
        t.append(f"{self.last['ptps']:6.1f} t/s", style=f"bold {C_USER}")
        t.append(f"  ({self.last['ptok']} tok)\n", style=C_DIM)
        t.append("last   ", style=C_DIM)
        t.append(f"{self.last['total']:.1f}s\n", style=C_TEXT)
        t.append("turns  ", style=C_DIM)
        t.append(f"{self.turns}   ", style=C_TEXT)
        t.append("tokens ", style=C_DIM)
        t.append(f"{self.total_gen_tokens}\n", style=C_TEXT)
        t.append_text(
            sparkline(self.tps_hist, width, vmax=max(20.0, max(self.tps_hist, default=0)))
        )
        self.query_one("#perf", Static).update(t)

        # Update browser & HAR panel
        tb = Text()
        cdp_connected = hasattr(self, "fetcher") and self.fetcher.is_connected()
        cdp_style = "bold #a6e3a1" if cdp_connected else "bold #6c7086"
        tb.append("cdp    ", style=C_DIM)
        tb.append(f"{'● connected' if cdp_connected else '○ offline'}", style=cdp_style)
        port_num = self.fetcher.port if hasattr(self, "fetcher") else 9226
        tb.append(f" (port {port_num})\n", style=C_DIM)

        tb.append("tab    ", style=C_DIM)
        tab_name = (self.fetcher.active_title or self.fetcher.active_url or "None") if hasattr(self, "fetcher") else "None"
        tb.append(f"{tab_name[:24]}\n", style=C_TEXT)

        har_summary = self.har.get_summary() if hasattr(self, "har") else {"is_capturing": False, "total_requests": 0, "api_requests": 0}
        har_style = "bold #f9e2af" if har_summary["is_capturing"] else C_DIM
        tb.append("har    ", style=C_DIM)
        tb.append(
            f"{'● recording' if har_summary['is_capturing'] else '○ idle'}",
            style=har_style,
        )
        tb.append(f"  {har_summary['total_requests']} reqs ({har_summary['api_requests']} APIs)", style=C_TEXT)
        try:
            self.query_one("#browser", Static).update(tb)
        except Exception:
            pass

        est = len(self.build_prompt()) // 4
        try:
            inp = self.query_one("#input", Input)
            inp.border_subtitle = f"ctx ≈{est}/{CTX}"
        except Exception:
            pass

        sb = Text()
        sb.append(" /help ", style=f"bold #11111b on {C_USER}")
        sb.append(f"  {self.state}", style=f"bold {state_style}")
        cdp_tag = f"● CDP:{port_num}" if cdp_connected else "○ CDP"
        har_tag = f"● HAR:{har_summary['total_requests']}" if har_summary["is_capturing"] else "○ HAR"
        sb.append(f"   {cdp_tag}", style="bold #a6e3a1" if cdp_connected else C_DIM)
        sb.append(f"   {har_tag}", style="bold #f9e2af" if har_summary["is_capturing"] else C_DIM)
        sb.append(f"   turns {self.turns}", style=C_DIM)
        sb.append(f"   ctx ≈{est}/{CTX}", style=C_DIM)
        sb.append(f"   {self.last['tps']:.1f} t/s", style=C_DIM)
        sb.append(f"   threads {THREADS}", style=C_DIM)
        try:
            self.query_one("#statusbar", Static).update(sb)
        except Exception:
            pass
        # Keep task progress bar alive / sized on resize
        try:
            self._render_taskbar()
        except Exception:
            pass

    # ── prompt building ──
    def build_prompt(self) -> str:
        prompt, _, _ = format_chat_prompt(ModelState.path, self.history, SYSTEM_PROMPT)
        return prompt

    # ── input handling ──
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
        if msg.startswith("/"):
            event.input.value = ""
            self._handle_command(msg[1:].strip())
            return
        # "print /path/to/file" or bare agent_runs path — never send to LLM
        print_path = self._extract_local_file_request(msg)
        if print_path:
            event.input.value = ""
            self.handle_print_cmd(print_path)
            return
        if self.busy:
            self.log_line(f"[{C_WARN}]busy — Ctrl+X to stop[/]")
            return
        # Auto-route browse/scrape intents into the CDP agent
        if self._looks_like_browser_goal(msg):
            event.input.value = ""
            self.log_line("[#a6e3a1]routing to /agent[/] (browser/scrape intent)")
            self.start_agent(msg)
            return
        event.input.value = ""
        self.add_message("user", msg)
        self.history.append(("user", msg))
        self.busy = True
        self.state = "loading"
        self.stop_flag = False
        self.live_widget = self.add_message("ai", "")
        self.live_widget.update(self._render_msg("ai", "", cursor=True))
        self.generate(self.build_prompt())

    @staticmethod
    def _extract_local_file_request(msg: str) -> str | None:
        """Detect print/cat/show of a local path (esp. agent_runs/*.jsonl)."""
        m = re.match(
            r"^(?:print|cat|show|read|open)\s+(\S+)",
            msg.strip(),
            re.I,
        )
        if m:
            return m.group(1).strip("'\"")
        # bare path to a run log / extract
        bare = msg.strip().strip("'\"")
        if bare.startswith("/") and (
            "/agent_runs/" in bare
            or bare.endswith((".jsonl", ".json", ".txt", ".log", ".md"))
        ):
            return bare
        return None

    @staticmethod
    def _looks_like_browser_goal(msg: str) -> bool:
        """Route plain-text scrape/geo/phone goals into /agent (skills path)."""
        low = msg.lower()
        verbs = (
            "go to", "open ", "navigate", "scrape", "scrap ", "browse",
            "google maps", "maps and", "click ", "fetch ",
            "give me", "get me", "find ", "list ", "we me",  # typo: give me
        )
        nouns = (
            "maps", "website", "url", "http://", "https://", "cdp", "pincode",
            "phone", "contact", "number",
        )
        geo = (
            "gujarat", "gujrat", "pune", "hinjewadi", "ahmedabad", "surat",
            "mumbai", "delhi", "bangalore", "india",
        )
        biz = (
            "hedge", "fund", "pharmacy", "pharmac", "restaurant", "hospital",
            "startup", "chemist", "hotel", "jewell", "jewel", "college", "school",
            "compan", "business", "firm", "shop", "store", "automation",
            "list of", "listing", "directory",
        )
        if any(v in low for v in verbs) and (
            any(n in low for n in nouns) or "scrape" in low or "scrap" in low
        ):
            return True
        # “phone numbers of hedge funds in gujarat” / “list of companies in pune”
        # → /agent → skills (Google Maps), not chat LLM
        contact = any(k in low for k in ("phone", "number", "contact", "email"))
        has_geo = any(g in low for g in geo)
        has_biz = any(b in low for b in biz)
        return (contact and (has_geo or has_biz)) or (has_biz and has_geo)

    def _handle_command(self, raw_cmd: str) -> None:
        parts = raw_cmd.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        dispatch = {
            "help": self.action_panel_help,
            "model": self.action_panel_model,
            "threads": self.action_panel_settings,
            "settings": self.action_panel_settings,
            "stats": self.action_panel_stats,
            "sessions": self.action_panel_sessions,
            "system": self.action_panel_system,
            "browser": self.action_panel_browser,
            "cron": self.action_panel_cron,
            "clear": self.action_clear,
            "reset": self.action_reset,
            "stop": self.action_stop,
            "save": self.action_save_session,
            "new": self.action_new_session,
        }
        if cmd in dispatch:
            dispatch[cmd]()
        elif cmd == "agent":
            if not arg:
                self.log_line(f"[{C_WARN}]Usage: /agent <goal>[/]")
                self.add_message("sys", "Usage: /agent <goal> — e.g. /agent research trending posts and capture traffic")
            else:
                self.start_agent(arg)
        elif cmd in ("fetch", "browse"):
            if not arg:
                self.log_line(f"[{C_WARN}]Usage: /{cmd} <url>[/]")
            else:
                self.start_fetch(arg)
        elif cmd == "click":
            if not arg:
                self.log_line(f"[{C_WARN}]Usage: /click <target_or_index>[/]")
            else:
                self.start_click(arg)
        elif cmd == "type":
            type_parts = arg.split(maxsplit=1)
            if len(type_parts) < 2:
                self.log_line(f"[{C_WARN}]Usage: /type <selector> <text>[/]")
            else:
                self.start_type(type_parts[0], type_parts[1])
        elif cmd == "har":
            self.handle_har_cmd(arg)
        elif cmd == "cdp":
            self.handle_cdp_cmd(arg)
        elif cmd in ("print", "cat", "show", "runlog"):
            path = arg.strip()
            if not path and cmd == "runlog":
                # latest run_*.jsonl
                runs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_runs")
                files = sorted(
                    (f for f in os.listdir(runs) if f.startswith("run_") and f.endswith(".jsonl")),
                    key=lambda f: os.path.getmtime(os.path.join(runs, f)),
                    reverse=True,
                ) if os.path.isdir(runs) else []
                path = os.path.join(runs, files[0]) if files else ""
            if not path:
                self.log_line(f"[{C_WARN}]Usage: /print <path>  or  /runlog[/]")
            else:
                self.handle_print_cmd(path)
        else:
            self.log_line(f"[{C_WARN}]unknown command: /{cmd}[/]")

    # ── browser & agent handlers ──
    def action_panel_browser(self) -> None:
        self.push_screen(BrowserScreen())

    def action_panel_cron(self) -> None:
        self.push_screen(CronScreen())

    def start_agent(self, goal: str) -> None:
        if self.busy:
            self.log_line(f"[{C_WARN}]busy — Ctrl+X to stop[/]")
            return
        self.add_message("user", f"/agent {goal}")
        self.busy = True
        self.state = "generating"
        self.stop_flag = False
        self.agent_worker(goal)

    @work(thread=True, exclusive=True)
    def agent_worker(self, goal: str) -> None:
        ui = self.call_from_thread
        t0 = time.time()
        ui(self.log_line, f"[bold #a6e3a1]Agent started:[/] {goal[:50]}")

        def llm_turn(prompt: str) -> str:
            if self.stop_flag:
                return "THOUGHT: Stopped by user.\nACTION: finish Process halted."
            return self._run_llm_single(prompt)

        def on_agent_event(event_type: str, data: Any):
            data = data or {}
            if event_type == "agent_started":
                ui(
                    self.set_task_progress,
                    active=True,
                    label=(data.get("goal") or goal)[:48],
                    step=0,
                    total=0,
                    phase="starting",
                    cards=0,
                    phones=0,
                    caution="",
                    overlap=None,
                    novelty=None,
                )
            elif event_type == "task_progress":
                ui(
                    self.set_task_progress,
                    active=True,
                    label=data.get("label") or goal[:48],
                    step=data.get("step", 0),
                    total=data.get("total", 0),
                    phase=data.get("phase") or "",
                    cards=data.get("cards", 0),
                    phones=data.get("phones", 0),
                    caution=data.get("caution") or "",
                    overlap=data.get("overlap"),
                    novelty=data.get("novelty"),
                )
                if data.get("caution"):
                    ui(self.log_line, f"[{C_WARN}]saturation:[/] {data.get('caution')}")
                elif data.get("phase"):
                    ui(
                        self.log_line,
                        f"progress {data.get('step', 0)}/{data.get('total', 0)} "
                        f"{data.get('phase')} cards={data.get('cards', 0)} "
                        f"phones={data.get('phones', 0)}",
                    )
            elif event_type == "agent_plan":
                tasks = data.get("tasks") or []
                lines = ["📋 Planned parallel CDP tasks:"]
                for t in tasks:
                    lines.append(f"  • {t.get('name')}: {t.get('goal')}")
                    if t.get("hint_url"):
                        lines.append(f"    → {t.get('hint_url')}")
                ui(self.add_message, "sys", "\n".join(lines))
                ui(self.log_line, f"plan: {len(tasks)} tasks")
                ui(
                    self.set_task_progress,
                    active=True,
                    label=goal[:48],
                    step=0,
                    total=len(tasks) or 0,
                    phase="planned",
                    tasks=tasks,
                )
            elif event_type == "step_action":
                step = data.get("step")
                thought = data.get("thought")
                act = data.get("action")
                arg = data.get("arg", "")
                if thought:
                    ui(self.add_message, "ai", f"🧠 [Step {step}] {thought}")
                ui(self.add_message, "sys", f"⚡ Action: {act} {arg}")
                ui(self.log_line, f"Step {step}: {act} {arg}")
                ui(
                    self.set_task_progress,
                    phase=f"{act}"[:40],
                    step=int(step) if isinstance(step, int) else 0,
                )
            elif event_type == "step_observation":
                obs = data.get("observation")
                ui(self.add_message, "sys", f"👁 Observation: {obs}")
                ui(self._agent_hist_append, f"[agent obs] {str(obs)[:500]}")
            elif event_type == "agent_finished":
                summary = data.get("summary")
                run_path = data.get("run_path", "")
                extracted = data.get("extracted") or {}
                mode = data.get("mode", "")
                cards_n = len(extracted.get("maps_cards") or [])
                phones_n = len(extracted.get("phones") or [])
                stopped = data.get("stopped")
                stop_reason = data.get("stop_reason") or ""
                dry = bool(data.get("dry_run"))
                blocked = bool(data.get("blocked"))
                ok = data.get("ok", True)
                extra = ""
                if mode:
                    extra += f"\nMode: {mode}" + (" (dry)" if dry else "")
                if cards_n:
                    extra += f"\nExtracted cards: {cards_n}"
                if phones_n:
                    extra += f"\nPhones: {phones_n}"
                pins = extracted.get("pincodes_sample") or []
                if pins:
                    extra += f"\nPincode sample: {', '.join(p.get('pincode','') for p in pins[:5])}"
                if stopped and stop_reason:
                    extra += f"\nStopped: {stop_reason}"
                if run_path:
                    extra += f"\nRun log: {run_path}"
                if blocked:
                    title = "Blocked — Chrome not running"
                    log_msg = "[bold #f9e2af]Agent blocked (no CDP)[/]"
                    phase = "blocked"
                elif dry and not cards_n and not phones_n:
                    title = "Dry plan only — nothing scraped"
                    log_msg = "[bold #f9e2af]Dry plan (no live scrape)[/]"
                    phase = "dry"
                elif stopped:
                    title = "Agent stopped"
                    log_msg = "[bold #f9e2af]Agent stopped[/]"
                    phase = "stopped"
                elif not ok:
                    title = "Agent finished with errors"
                    log_msg = "[bold #f38ba8]Agent finished with errors[/]"
                    phase = "error"
                else:
                    title = "Goal Accomplished"
                    log_msg = "[bold #a6e3a1]Agent goal completed[/]"
                    phase = "done"
                ui(self.add_message, "ai", f"{title}:\n{summary}{extra}")
                ui(self._agent_hist_append, f"[agent done] {summary}")
                ui(self.log_line, log_msg)
                ui(
                    self.set_task_progress,
                    active=True,
                    phase=phase,
                    cards=cards_n,
                    phones=phones_n,
                    caution=stop_reason if stopped else ("CDP offline" if (dry or blocked) else ""),
                    step=1,
                    total=1,
                )

        self.agent = OrchestratorAgent(
            llm_fn=llm_turn,
            page_fetcher=self.fetcher,
            har_manager=self.har,
            ui_callback=on_agent_event,
        )

        try:
            # Skills path auto-starts Chrome for live scrape unless goal says "dry"
            summary = self.agent.run_goal(goal, max_steps=20)
        except Exception as e:
            ui(self.add_message, "sys", f"⚠️ Agent error: {e}")
            ui(self.log_line, f"[{C_ERR}]Agent exception: {e}[/]")
        finally:
            self.agent = None
            ui(self._agent_done, time.time() - t0)

    def _agent_hist_append(self, text: str) -> None:
        self.history.append(("assistant", text))

    def _agent_done(self, elapsed: float) -> None:
        self.busy = False
        self.state = "idle"
        self.log_line(f"agent finished in {elapsed:.1f}s")

    def _run_llm_single(self, prompt: str) -> str:
        prompt_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=HOME, encoding="utf-8") as f:
                f.write(prompt)
                prompt_path = f.name

            model_path = ModelState.path
            _, marker, stops = format_chat_prompt(model_path, [], "")
            flags = llama_flags()
            cmd = [
                LLAMA_BIN, "-m", model_path, "-f", prompt_path,
                "-n", str(N_PREDICT), "-t", str(THREADS), "-c", str(CTX),
                "-ngl", "0", "-b", "512",
                "--temp", str(TEMP), "--top-p", str(TOP_P),
                "--repeat-penalty", str(REPEAT_PENALTY),
            ]
            if flags.get("no_cnv"):
                cmd.append(flags["no_cnv"])
            if flags.get("simple_io"):
                cmd.append(flags["simple_io"])
            if flags.get("no_display_prompt"):
                cmd.append(flags["no_display_prompt"])

            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
            raw = proc.stdout
            if marker in raw:
                gen = raw.split(marker)[-1]
                if gen.startswith("\n"):
                    gen = gen[1:]
            else:
                gen = raw

            for s in stops:
                if s in gen:
                    gen = gen.split(s)[0]
            return gen.strip()
        except Exception as e:
            return f"LLM error: {e}"
        finally:
            if prompt_path and os.path.exists(prompt_path):
                try:
                    os.unlink(prompt_path)
                except Exception:
                    pass

    def start_fetch(self, url: str) -> None:
        if self.busy:
            self.log_line(f"[{C_WARN}]busy — Ctrl+X first[/]")
            return
        self.add_message("user", f"/fetch {url}")
        self.busy = True
        self.state = "loading"
        self.fetch_worker(url)

    @work(thread=True)
    def fetch_worker(self, url: str) -> None:
        ui = self.call_from_thread
        ui(self.log_line, f"Fetching page: {url}…")
        snap = self.fetcher.fetch(url)
        summary = snap.summary(max_text_chars=1200)
        ui(self.add_message, "sys", f"📄 [bold]{snap.title}[/]\n{summary}")
        self.history.append(("user", f"Here is the page content of {snap.url} ({snap.title}):\n{summary}"))
        self.history.append(("assistant", f"I have loaded and reviewed {snap.title}. How would you like me to help you with it?"))
        ui(self.log_line, f"Page loaded: {snap.title} ({len(snap.interactives)} interactives)")
        ui(self._agent_done, 1.0)

    def start_click(self, target: str) -> None:
        self.add_message("user", f"/click {target}")
        res = self.fetcher.click(target)
        if res.get("success"):
            self.add_message("sys", f"✓ Clicked: {res.get('text', target)}")
            self.log_line(f"Clicked element: {target}")
        else:
            self.add_message("sys", f"⚠️ Click failed: {res.get('error', 'Unknown')}")
            self.log_line(f"[{C_WARN}]Click failed: {res.get('error')}[/]")

    def start_type(self, selector: str, text: str) -> None:
        self.add_message("user", f"/type {selector} {text}")
        res = self.fetcher.type_text(selector, text)
        if res.get("success"):
            self.add_message("sys", f"✓ Typed text into: {selector}")
            self.log_line(f"Typed into {selector}")
        else:
            self.add_message("sys", f"⚠️ Typing failed: {res.get('error', 'Unknown')}")
            self.log_line(f"[{C_WARN}]Typing failed: {res.get('error')}[/]")

    def handle_print_cmd(self, path: str) -> None:
        """Show a local file in chat (pretty-print json/jsonl). Never hits the LLM."""
        path = os.path.expanduser((path or "").strip().strip("'\""))
        self.add_message("user", f"/print {path}")
        if not path:
            self.add_message("sys", "Usage: /print <path> · /runlog · or: print /path/to/file")
            return
        if not os.path.isfile(path):
            self.log_line(f"[{C_WARN}]not found:[/] {path}")
            self.add_message("sys", f"File not found: {path}")
            return
        try:
            size = os.path.getsize(path)
            max_bytes = 120_000
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            if truncated:
                raw = raw[:max_bytes]

            lines_out: list[str] = [
                f"[b]{os.path.basename(path)}[/b]  ({size} bytes"
                + (", truncated" if truncated else "")
                + ")",
                f"[dim]{path}[/dim]",
                "",
            ]
            if path.endswith(".jsonl"):
                for i, line in enumerate(raw.splitlines(), 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        pretty = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
                    except Exception:
                        pretty = line
                    # keep chat usable — cap each event
                    if len(pretty) > 4000:
                        pretty = pretty[:4000] + "\n… (event truncated)"
                    lines_out.append(f"[#89b4fa]── event {i} ──[/]")
                    lines_out.append(pretty)
                    lines_out.append("")
                    if i >= 40:
                        lines_out.append("[dim]… more events omitted[/dim]")
                        break
            elif path.endswith(".json"):
                try:
                    obj = json.loads(raw)
                    pretty = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
                except Exception:
                    pretty = raw
                if len(pretty) > 12000:
                    pretty = pretty[:12000] + "\n… (truncated)"
                lines_out.append(pretty)
            else:
                text = raw if len(raw) <= 12000 else raw[:12000] + "\n… (truncated)"
                lines_out.append(text)

            self.add_message("sys", "\n".join(lines_out))
            self.log_line(f"[#a6e3a1]printed[/] {os.path.basename(path)}")
        except Exception as e:
            self.log_line(f"[{C_ERR}]print failed:[/] {e}")
            self.add_message("sys", f"print failed: {e}")

    def handle_har_cmd(self, arg: str) -> None:
        sub = arg.strip().lower()
        if sub == "start":
            ok = self.har.start_capture(self.fetcher.port)
            if ok:
                self.log_line("[#a6e3a1]HAR capture started on browser CDP stream[/]")
                self.add_message("sys", "● HAR network capture started.")
            else:
                self.log_line(f"[{C_ERR}]Failed to start HAR capture (connect Chrome first with /cdp)[/]")
                self.add_message("sys", "⚠️ Could not attach HAR capture. Ensure Chrome is running with remote debugging.")
        elif sub == "stop":
            summary = self.har.stop_capture()
            self.log_line(f"HAR capture stopped ({summary['total_requests']} requests)")
            self.add_message(
                "sys",
                f"■ HAR capture stopped.\nTotal requests: {summary['total_requests']} ({summary['api_requests']} API calls, {summary['total_domains']} domains)\nUse [b]/har save[/b] to write to file.",
            )
        elif sub.startswith("save"):
            parts = sub.split(maxsplit=1)
            filename = parts[1] if len(parts) > 1 else None
            filepath, count = self.har.save_har(filename)
            self.log_line(f"HAR saved: {os.path.basename(filepath)} ({count} reqs)")
            self.add_message("sys", f"💾 Saved HAR archive ({count} requests) to:\n{filepath}")
        else:
            summary = self.har.get_summary()
            status = "RECORDING" if summary["is_capturing"] else "IDLE"
            self.add_message(
                "sys",
                f"HAR Status: [b]{status}[/b]\nRequests: {summary['total_requests']} | APIs: {summary['api_requests']} | Duration: {summary['duration_seconds']}s\nDomains: {', '.join(summary['domains']) or '(none)'}",
            )

    def handle_cdp_cmd(self, arg: str) -> None:
        port = int(arg.strip()) if arg.strip().isdigit() else None
        if port:
            ok = self.fetcher.connect(port)
        else:
            found = self.fetcher.find_available_port()
            ok = self.fetcher.connect(found) if found else False

        if ok:
            self.log_line(f"[#a6e3a1]Connected to Chrome CDP on port {self.fetcher.port}[/]")
            self.add_message(
                "sys",
                f"✓ Connected to Chrome CDP on port {self.fetcher.port}.\nActive Tab: {self.fetcher.active_title} ({self.fetcher.active_url})",
            )
        else:
            self.log_line(f"[{C_WARN}]Could not connect to Chrome CDP on port {self.fetcher.port}[/]")
            self.add_message(
                "sys",
                f"⚠️ Chrome CDP not found on port {self.fetcher.port}.\nStart Chrome with: [b]google-chrome --remote-debugging-port={self.fetcher.port}[/b] or run [b]python launch-chrome.py[/b]. (Direct HTTP /fetch still works!)",
            )

    # ── actions ──
    def action_stop(self) -> None:
        if self.agent:
            self.agent.stop()
        if self.busy and self.proc:
            self.stop_flag = True
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.log_line(f"[{C_WARN}]stopped by user[/]")

    def action_clear(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        for child in list(chat.children):
            child.remove()
        self.log_line("screen cleared")

    def action_reset(self) -> None:
        self.history.clear()
        self.turns = 0
        self.log_line("conversation memory reset")

    def action_new_session(self) -> None:
        self.history.clear()
        self.turns = 0
        self.total_gen_tokens = 0
        chat = self.query_one("#chat", VerticalScroll)
        for child in list(chat.children):
            child.remove()
        self.add_message("sys", "New session. Type below to begin.")
        self.log_line("new session started")

    def action_save_session(self) -> None:
        self.push_screen(SessionScreen())

    def action_panel_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_panel_model(self) -> None:
        self.push_screen(ModelScreen())

    def action_panel_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_panel_stats(self) -> None:
        self.push_screen(StatsScreen())

    def action_panel_sessions(self) -> None:
        self.push_screen(SessionScreen())

    def action_panel_system(self) -> None:
        self.push_screen(SystemScreen())

    # ── model switch (called by ModelScreen) ──
    def _apply_model_switch(self, new_path: str) -> None:
        if self.busy:
            self.log_line(f"[{C_WARN}]cannot switch while generating — Ctrl+X first[/]")
            return
        old = ModelState.path
        ModelState.path = new_path
        self.history.clear()
        self.turns = 0
        self.total_gen_tokens = 0
        self.last = {"tps": 0.0, "ptps": 0.0, "ptok": 0, "gtok": 0, "total": 0.0}
        chat = self.query_one("#chat", VerticalScroll)
        for child in list(chat.children):
            child.remove()
        self.add_message(
            "sys",
            f"switched model → {os.path.basename(new_path)}  (conversation reset)",
        )
        self.log_line(
            f"model: [b]{os.path.basename(old) if old else '?'}[/b] → "
            f"[b]{os.path.basename(new_path)}[/b]"
        )
        if is_probably_vocab(new_path):
            self.log_line(
                f"[{C_ERR}]warning: chosen model looks like vocab-only/tiny file — "
                f"generation will likely fail[/]"
            )
        if not os.path.exists(LLAMA_BIN):
            self.log_line(f"[{C_ERR}]llama-cli still missing:[/] {LLAMA_BIN}")

    # ── generation (worker thread) ──
    @staticmethod
    def _visible(buf: str):
        cut = None
        for m in STOP_MARKERS:
            i = buf.find(m)
            if i != -1 and (cut is None or i < cut):
                cut = i
        if cut is not None:
            return buf[:cut], True
        for m in STOP_MARKERS:
            for k in range(len(m) - 1, 0, -1):
                if buf.endswith(m[:k]):
                    return buf[:-k], False
        return buf, False

    @work(thread=True, exclusive=True)
    def generate(self, prompt: str) -> None:
        ui = self.call_from_thread
        t0 = time.time()
        prompt_path = None
        reply = ""
        err_chunks = []
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, dir=HOME, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_path = f.name

            model_path = ModelState.path
            _, marker, stops = format_chat_prompt(model_path, [], "")
            flags = llama_flags()
            cmd = [
                LLAMA_BIN, "-m", model_path, "-f", prompt_path,
                "-n", str(N_PREDICT), "-t", str(THREADS), "-c", str(CTX),
                "-ngl", "0", "-b", "512",
                "--temp", str(TEMP), "--top-p", str(TOP_P),
                "--repeat-penalty", str(REPEAT_PENALTY),
            ]
            if flags.get("no_cnv"):
                cmd.append(flags["no_cnv"])
            if flags.get("simple_io"):
                cmd.append(flags["simple_io"])
            if flags.get("no_display_prompt"):
                cmd.append(flags["no_display_prompt"])

            ui(self.log_line, "spawning llama-cli…")
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )

            def drain():
                try:
                    for chunk in iter(lambda: self.proc.stderr.read(4096), b""):
                        err_chunks.append(chunk)
                except Exception:
                    pass

            threading.Thread(target=drain, daemon=True).start()

            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            raw = ""
            last_ui = 0.0
            first = True
            self.gen_tokens = 0
            self.gen_start = 0.0
            fd = self.proc.stdout.fileno()
            hit_stop = False

            while True:
                if time.time() - t0 > TIMEOUT_S:
                    self.proc.kill()
                    ui(self.log_line, f"[{C_ERR}]timeout after {TIMEOUT_S}s[/]")
                    break
                data = os.read(fd, 256)
                if not data:
                    break
                if first:
                    first = False
                    self.state = "generating"
                    self.gen_start = time.time()
                    try:
                        if psutil:
                            self.proc_rss = psutil.Process(self.proc.pid).memory_info().rss
                    except Exception:
                        pass
                raw += decoder.decode(data)

                # Check if generation has started past marker
                if marker in raw:
                    content = raw.split(marker)[-1]
                    if content.startswith("\n"):
                        content = content[1:]

                    cut = None
                    for s in stops:
                        i = content.find(s)
                        if i != -1 and (cut is None or i < cut):
                            cut = i
                    if cut is not None:
                        reply = content[:cut]
                        hit_stop = True
                    else:
                        reply = content
                        self.gen_tokens += 1
                else:
                    reply = ""

                now = time.time()
                if now - last_ui > 0.08 and reply:
                    last_ui = now
                    shown = reply.lstrip()
                    ui(self._update_live, shown, True)
                if hit_stop:
                    try:
                        self.proc.terminate()
                    except Exception:
                        pass
                    break

            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()

            if marker in raw:
                content = raw.split(marker)[-1]
                if content.startswith("\n"):
                    content = content[1:]
                for s in stops:
                    if s in content:
                        content = content.split(s)[0]
                reply = content.strip()
            else:
                reply = ""
            stderr_text = b"".join(err_chunks).decode("utf-8", "replace")

            if not reply:
                if self.stop_flag:
                    reply = "[stopped]"
                else:
                    # Figure out why the spawn produced nothing.
                    low = stderr_text.lower()
                    hint = ""
                    if "invalid argument" in low:
                        m = re.search(r"invalid argument:\s*(\S+)", low)
                        arg = m.group(1) if m else "?"
                        hint = f" [flag rejected: {arg} — check llama-cli --help]"
                    elif (
                        "failed to load model" in low
                        or "unable to load model" in low
                        or "error loading model" in low
                    ):
                        hint = " [model failed to load — check path/quant]"
                    elif is_probably_vocab(model_path):
                        hint = " [tiny/vocab file — not a usable model]"
                    elif "unknown argument" in low:
                        hint = " [unknown flag — check llama-cli --help]"
                    reply = f"[empty response{hint}]"
                    tail = stderr_text.strip().splitlines()[-5:]
                    for line in tail:
                        ui(self.log_line, f"[{C_DIM}]{line[:120]}[/]")
            ui(self._finish, reply, stderr_text, time.time() - t0)

        except FileNotFoundError:
            ui(
                self._finish,
                f"[Error: llama binary not found at {LLAMA_BIN}]",
                "",
                time.time() - t0,
                True,
            )
        except PermissionError:
            ui(
                self._finish,
                f"[Error: llama binary not executable: {LLAMA_BIN}]",
                "",
                time.time() - t0,
                True,
            )
        except Exception as e:  # noqa: BLE001
            ui(self._finish, f"[Error: {str(e)[:120]}]", "", time.time() - t0, True)
        finally:
            if prompt_path:
                try:
                    os.unlink(prompt_path)
                except Exception:
                    pass

    # ── back on the UI thread ──
    def _update_live(self, text: str, cursor: bool) -> None:
        if not self.live_widget:
            return
        try:
            self.live_widget.update(self._render_msg("ai", text, cursor=cursor))
            self.query_one("#chat", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def _finish(self, reply: str, stderr_text: str, elapsed: float, error: bool = False) -> None:
        self._update_live(reply, False)
        if not error and not reply.startswith("["):
            self.history.append(("assistant", reply))
            self.turns += 1
        elif self.history and self.history[-1][0] == "user":
            self.history.pop()

        m = re.search(
            r"llama_perf_context_print:\s+eval time\s*=\s*([\d.]+) ms /\s*(\d+) runs.*?([\d.]+) tokens per second",
            stderr_text,
        )
        if m:
            self.last["gtok"] = int(m.group(2))
            self.last["tps"] = float(m.group(3))
            self.total_gen_tokens += int(m.group(2))
            self.tps_hist.append(float(m.group(3)))
        m = re.search(
            r"prompt eval time\s*=\s*([\d.]+) ms /\s*(\d+) tokens.*?([\d.]+) tokens per second",
            stderr_text,
        )
        if m:
            self.last["ptok"] = int(m.group(2))
            self.last["ptps"] = float(m.group(3))
        self.last["total"] = elapsed
        self.log_line(f"done in {elapsed:.1f}s · {self.last['tps']:.1f} t/s")

        self.busy = False
        self.state = "idle"
        self.proc = None
        self.proc_rss = 0
        self.live_widget = None
        try:
            self.query_one("#input", Input).focus()
        except Exception:
            pass


if __name__ == "__main__":
    if not os.path.exists(ModelState.path):
        print(f"Model not found: {ModelState.path}", file=sys.stderr)
    if not os.path.exists(LLAMA_BIN):
        print(f"llama-cli not found: {LLAMA_BIN}", file=sys.stderr)
    LlamaTUI().run()
