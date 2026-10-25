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

Local source (current directory only, results stay in the chat context):
    ; read codebase                 load source files from the cwd
    ; cat <file>                    print a file
    ; sed -n '1,80p' <file>         print a line range
    ; sed -i 's/old/new/g' <file>   substitute inside a file
    /sh <those same commands>

Model discovery: scans $LLAMA_MODEL_DIR, ~/llama.cpp/models, ~/.llama-tui/models
(recursively, depth ≤ 2) for *.gguf. Vocab-only and tiny files (<10 MB) are
filtered out. Switch live via F2 / /model.

Optional: `pip install psutil` for per-process stats (falls back to /proc).
"""

import codecs
import difflib
import importlib
import importlib.util
import inspect
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
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
LLAMA_SERVER_BIN = os.environ.get(
    "LLAMA_SERVER_BIN", os.path.join(LLAMA_DIR, "build/bin/llama-server")
)
LLAMA_SERVER_PORT = int(os.environ.get("LLAMA_SERVER_PORT", "8491"))
LLAMA_SERVER_HOST = "127.0.0.1"

# Directories scanned for *.gguf. First match wins for display order.
# Also scans HuggingFace hub cache for downloaded GGUF blobs.
_HF_CACHE = os.path.join(HOME, ".cache", "huggingface", "hub")
_HF_GGUF_DIRS = []
if os.path.isdir(_HF_CACHE):
    for _repo in os.listdir(_HF_CACHE):
        _snap = os.path.join(_HF_CACHE, _repo, "snapshots")
        if not os.path.isdir(_snap):
            continue
        for _rev in os.listdir(_snap):
            _rev_path = os.path.join(_snap, _rev)
            if os.path.isdir(_rev_path):
                _HF_GGUF_DIRS.append(_rev_path)

MODEL_DIRS = [
    d
    for d in (
        [os.environ.get("LLAMA_MODEL_DIR")]
        + [os.path.join(LLAMA_DIR, "models")]
        + [os.path.join(HOME, ".llama-tui", "models")]
        + _HF_GGUF_DIRS
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

# DeepSeek-R1 needs much more room for <think> reasoning chains
_DS_R1_CTX = 8192
_DS_R1_N_PREDICT = 2048
_DS_R1_TIMEOUT = 600
MAX_PROMPT_CHARS = 3200
SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and concisely."
DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT

SESS_DIR = os.path.join(HOME, ".llama-tui", "sessions")
TODO_PATH = os.path.join(HOME, ".llama-tui", "todo.json")
SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent", "skills")

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

# ───────────────────────── workspace commands (; cat / ; sed) ─────────────────────────
# Results are jailed to the process cwd. The model never gets a shell.
WORKSPACE_DISPLAY_CHARS = 14_000
WORKSPACE_HISTORY_CHARS = 4_000
_CODEBASE_BODY_BUDGET = 3_500
_CODEBASE_FILE_CAP = 1_200
_CODEBASE_TREE_CAP = 250
_CMD_TIMEOUT_S = 15
_MAX_FILE_BYTES = 1_000_000

_SAFE_CMDS = frozenset({
    "cat", "sed", "ls", "head", "tail", "wc", "grep", "rg", "find", "pwd", "nl",
})
_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "agent_runs", "logs", "dist", "build", ".mypy_cache", ".pytest_cache",
    "data",
})
_SOURCE_EXTS = frozenset({
    ".py", ".js", ".md", ".sh", ".toml", ".yml", ".yaml",
    ".css", ".html", ".txt", ".rhai", ".json",
})
_SECRET_NAMES = frozenset({
    "credentials.json", "token.json", "secrets.json", "id_rsa", "id_ed25519",
})
_OPTS_WITH_ARG = {
    "head": {"-n", "-c", "--lines", "--bytes"},
    "tail": {"-n", "-c", "--lines", "--bytes"},
    "nl": {"-s", "-w", "-v", "-i", "-b"},
    "grep": {
        "-e", "-f", "-m", "-A", "-B", "-C",
        "--regexp", "--file", "--max-count", "--include", "--exclude", "--exclude-dir",
    },
    "rg": {"-e", "-g", "-t", "-m", "-A", "-B", "-C", "--max-count"},
    "find": {
        "-name", "-iname", "-path", "-regex", "-maxdepth", "-mindepth",
        "-type", "-size", "-mtime", "-mmin",
    },
}
_FIND_DENIED = frozenset({
    "-exec", "-execdir", "-ok", "-okdir", "-delete",
    "-fls", "-fprint", "-fprintf", "-fprint0",
})
_SHELL_TOKENS = frozenset({"|", "||", "&", "&&", ";", ">", ">>", "<", "<<"})
_SED_RANGE = re.compile(r"^(\d+)(,(\d+|\$))?p$")
_SED_SUB = re.compile(
    r"^s(?P<d>[^\s\\])(?:\\.|(?!(?P=d)).)*?(?P=d)"
    r"(?:\\.|(?!(?P=d)).)*?(?P=d)[gimpI0-9]*$"
)
_CODEBASE_RE = re.compile(
    r"^(?:please\s+)?"
    r"(?:read|load|show|dump)"
    r"\s+(?:the\s+|my\s+|this\s+)?"
    r"(?:codebase|code\s*base|source(?:\s+code)?|repo(?:sitory)?)"
    r"(?:\s+of\s+the\s+current\s+(?:directory|dir|folder))?"
    r"\s*$",
    re.IGNORECASE,
)
_CAT_CODEBASE_RE = re.compile(
    r"^cat\s+(?:the\s+)?(?:codebase|source\s+code)"
    r"(?:\s+of\s+the\s+current\s+(?:directory|dir|folder))?"
    r"\s*$",
    re.IGNORECASE,
)


class WorkspaceError(Exception):
    """A local source command was rejected or failed closed."""


def _is_secret(path: str) -> bool:
    base = os.path.basename(path)
    return (
        base in _SECRET_NAMES
        or base == ".env"
        or base.startswith(".env.")
        or base.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _resolve_in_workspace(token: str, workspace: str) -> str:
    if token in {"-", ""}:
        raise WorkspaceError("stdin is disabled; pass a file in the current directory")
    raw = token if os.path.isabs(token) else os.path.join(workspace, token)
    real = os.path.realpath(raw)
    root = os.path.realpath(workspace)
    if real != root and not real.startswith(root + os.sep):
        raise WorkspaceError(f"path is outside the current directory: {token}")
    if _is_secret(real):
        raise WorkspaceError(f"refusing secret file: {os.path.basename(real)}")
    return real


def _rel(path: str, workspace: str) -> str:
    return os.path.relpath(path, os.path.realpath(workspace))


def classify_workspace_input(msg: str, workspace: str) -> bool:
    """True when this line is a local source command, not chat."""
    raw = (msg or "").strip()
    if not raw:
        return False
    if raw.startswith(";"):
        return True
    if _CODEBASE_RE.match(raw) or _CAT_CODEBASE_RE.match(raw):
        return True
    return _looks_like_shell(raw, workspace)


def _looks_like_shell(body: str, workspace: str) -> bool:
    try:
        argv = shlex.split(body, posix=True)
    except ValueError:
        return False
    if not argv or argv[0].lower() not in _SAFE_CMDS:
        return False
    if len(argv) == 1:
        return argv[0].lower() in {"ls", "pwd"}
    return any(_token_is_pathish(tok, workspace) for tok in argv[1:])


def _token_is_pathish(tok: str, workspace: str) -> bool:
    if tok.startswith("-") or tok[:1].isdigit() or any(c in tok for c in "/*.$~"):
        return True
    return os.path.exists(os.path.join(workspace, tok))


def run_workspace_line(msg: str, workspace: str) -> str:
    """Run one jailed source command. Raises WorkspaceError."""
    body = re.sub(r"^;+\s*", "", (msg or "").strip()).strip()
    if not body:
        raise WorkspaceError(
            "empty command. try: ; read codebase   ; cat <file>   ; sed -n '1,40p' <file>"
        )
    if _CODEBASE_RE.match(body) or _CAT_CODEBASE_RE.match(body):
        return read_codebase(workspace)
    try:
        argv = shlex.split(body, posix=True)
    except ValueError as exc:
        raise WorkspaceError(f"could not parse command: {exc}") from exc
    if not argv:
        raise WorkspaceError("empty command")
    if any(tok in _SHELL_TOKENS or "`" in tok or "$(" in tok for tok in argv):
        raise WorkspaceError("pipes, redirects, and shell substitution are disabled")
    if argv[0] == "read" and len(argv) == 2:
        argv[0] = "cat"
    return exec_workspace(argv, workspace)


def read_codebase(workspace: str) -> str:
    """List source files under workspace and inline as many as the context budget allows."""
    root = os.path.realpath(workspace)
    if not os.path.isdir(root):
        raise WorkspaceError(f"current directory is not a directory: {workspace}")
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.startswith(".") or _is_secret(name):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _SOURCE_EXTS:
                continue
            full = os.path.join(dirpath, name)
            real = os.path.realpath(full)
            if real != root and not real.startswith(root + os.sep):
                continue
            if _is_secret(real):
                continue
            try:
                if os.path.getsize(real) > 256_000:
                    continue
            except OSError:
                continue
            found.append(real)
            if len(found) >= _CODEBASE_TREE_CAP:
                break
        if len(found) >= _CODEBASE_TREE_CAP:
            break
    found.sort(key=lambda p: (_rel(p, root).count("/"), _rel(p, root)))
    lines = [
        f"workspace: {root}",
        f"source files: {len(found)}"
        + (" (listing capped)" if len(found) >= _CODEBASE_TREE_CAP else ""),
        "commands: ; cat <file>    ; sed -n '1,80p' <file>    ; sed -i 's/old/new/g' <file>",
        "",
        "tree:",
    ]
    for path in found:
        lines.append(f"  {_rel(path, root)}")
    lines.append("")
    budget = _CODEBASE_BODY_BUDGET
    shown = 0
    for path in found:
        if budget <= 0:
            break
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                blob = fh.read(_CODEBASE_FILE_CAP + 1)
        except OSError as exc:
            lines.append(f"## {_rel(path, root)}  ({exc})")
            continue
        if "\x00" in blob:
            continue
        take = min(_CODEBASE_FILE_CAP, budget)
        clipped = len(blob) > take
        body = blob[:take]
        budget -= len(body)
        shown += 1
        rel = _rel(path, root)
        lines.append(f"## {rel}" + ("  (clipped)" if clipped else ""))
        lines.append(body.rstrip())
        lines.append("")
    if shown < len(found):
        lines.append(
            f"(inlined {shown} of {len(found)} files — "
            "; cat <file> or ; sed -n 'A,Bp' <file> for the rest)"
        )
    return "\n".join(lines).rstrip() + "\n"


def exec_workspace(argv: list[str], workspace: str) -> str:
    cmd = argv[0]
    if os.path.basename(cmd) != cmd or cmd not in _SAFE_CMDS:
        raise WorkspaceError(
            "allowed commands: "
            + " ".join(sorted(_SAFE_CMDS))
            + "    or: ; read codebase"
        )
    if cmd == "pwd":
        if len(argv) != 1:
            raise WorkspaceError("pwd takes no arguments")
        return os.path.realpath(workspace) + "\n"
    if cmd == "sed":
        return _run_sed(argv, workspace)
    path_idx = _path_indexes(cmd, argv)
    resolved_argv = list(argv)
    paths: list[str] = []
    for i in path_idx:
        real = _resolve_in_workspace(argv[i], workspace)
        resolved_argv[i] = real
        paths.append(real)
    if cmd in {"cat", "head", "tail", "nl", "wc"} and not paths:
        raise WorkspaceError(f"{cmd} needs a file in the current directory")
    for path in paths:
        if os.path.isfile(path) and os.path.getsize(path) > _MAX_FILE_BYTES:
            raise WorkspaceError(
                f"{_rel(path, workspace)} is over 1 MB; use ; sed -n 'A,Bp' {_rel(path, workspace)}"
            )
    if cmd == "grep":
        resolved_argv = [
            "grep",
            "--exclude-dir=.git",
            "--exclude-dir=__pycache__",
            "--exclude=credentials.json",
            "--exclude=token.json",
            "--exclude=secrets.json",
            "--exclude=.env",
            "--exclude=*.pem",
            "--exclude=*.key",
            "--exclude=*.p12",
            *resolved_argv[1:],
        ]
    text, _code = _run_argv(resolved_argv, workspace)
    return text


def _path_indexes(cmd: str, argv: list[str]) -> list[int]:
    take_arg = _OPTS_WITH_ARG.get(cmd, set())
    idxs: list[int] = []
    i = 1
    pattern_taken = cmd not in {"grep", "rg"}
    find_expr = False
    while i < len(argv):
        arg = argv[i]
        if cmd == "find" and arg in _FIND_DENIED:
            raise WorkspaceError(f"find {arg} is disabled")
        if arg == "--":
            idxs.extend(range(i + 1, len(argv)))
            break
        if arg in take_arg:
            if cmd == "find":
                find_expr = True
            if cmd in {"grep", "rg"} and arg in {"-e", "--regexp"}:
                pattern_taken = True
            i += 2
            continue
        if arg.startswith("-"):
            if cmd == "find":
                find_expr = True
            i += 1
            continue
        if cmd == "find" and find_expr:
            raise WorkspaceError(f"unexpected find argument: {arg}")
        if not pattern_taken:
            pattern_taken = True
            i += 1
            continue
        idxs.append(i)
        i += 1
    if cmd == "find" and not idxs:
        argv.append(".")
        idxs.append(len(argv) - 1)
    return idxs


def _check_sed_script(script: str) -> None:
    if "\n" in script or "\x00" in script:
        raise WorkspaceError("sed script must be one line")
    if _SED_RANGE.fullmatch(script) or _SED_SUB.fullmatch(script):
        return
    raise WorkspaceError(
        "sed supports a line range or one substitution: "
        "; sed -n '1,80p' FILE    or    ; sed -i 's/old/new/g' FILE"
    )


def _prepare_sed(argv: list[str], workspace: str) -> tuple[list[str], list[str], bool]:
    flags: list[str] = []
    scripts: list[str] = []
    files: list[str] = []
    seen_script = False
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            files.extend(argv[i + 1:])
            break
        if arg in {"-e", "--expression"}:
            if i + 1 >= len(argv):
                raise WorkspaceError("sed -e needs a script")
            _check_sed_script(argv[i + 1])
            scripts.append(argv[i + 1])
            seen_script = True
            i += 2
            continue
        if arg in {"-f", "--file"}:
            raise WorkspaceError("sed -f is disabled; pass the script with -e or as the first argument")
        if arg in {"-n", "--quiet", "--silent"}:
            if "-n" not in flags:
                flags.append("-n")
            i += 1
            continue
        if arg in {"-E", "-r", "--regexp-extended"}:
            if "-E" not in flags:
                flags.append("-E")
            i += 1
            continue
        if arg in {"-i", "--in-place"}:
            if "-i" not in flags:
                flags.append("-i")
            i += 1
            continue
        if (arg.startswith("-i") and arg != "-i") or arg.startswith("--in-place="):
            suffix = arg[2:] if arg.startswith("-i") else arg.split("=", 1)[1]
            if not re.fullmatch(r"\.?[A-Za-z0-9_-]+", suffix or ""):
                raise WorkspaceError("sed -i suffix must look like .bak")
            flags.append(arg if arg.startswith("-i") else f"-i{suffix}")
            i += 1
            continue
        if arg.startswith("-"):
            raise WorkspaceError(f"sed flag not allowed: {arg}")
        if not seen_script:
            _check_sed_script(arg)
            scripts.append(arg)
            seen_script = True
            i += 1
            continue
        files.append(arg)
        i += 1
    if not seen_script:
        raise WorkspaceError("sed needs a script")
    if not files:
        raise WorkspaceError("sed needs a file in the current directory")
    if all(_SED_RANGE.fullmatch(s) for s in scripts) and "-n" not in flags:
        flags.insert(0, "-n")
    resolved = [_resolve_in_workspace(tok, workspace) for tok in files]
    for path in resolved:
        if os.path.isfile(path) and os.path.getsize(path) > _MAX_FILE_BYTES:
            raise WorkspaceError(f"{_rel(path, workspace)} is over 1 MB")
    out = ["sed", *flags]
    for script in scripts:
        out.extend(["-e", script])
    out.extend(resolved)
    inplace = any(f == "-i" or f.startswith("-i") for f in flags)
    return out, resolved, inplace


def _run_sed(argv: list[str], workspace: str) -> str:
    cleaned, paths, inplace = _prepare_sed(argv, workspace)
    before: dict[str, bytes] = {}
    if inplace:
        for path in paths:
            with open(path, "rb") as fh:
                before[path] = fh.read()
    try:
        text, code = _run_argv(cleaned, workspace)
    except WorkspaceError:
        _restore_files(before)
        raise
    if code != 0:
        if before:
            _restore_files(before)
            return text.rstrip() + "\n(file restored)\n"
        return text
    if inplace and before:
        emptied = _empty_inplace(before)
        if emptied:
            raise WorkspaceError(
                "sed -i would empty "
                + ", ".join(_rel(p, workspace) for p in emptied)
                + "; restored"
            )
        diffs = _inplace_diffs(before, workspace)
        extra = ""
        if text.strip() and text.strip() != "(no output)":
            extra = "\n" + text
        return (diffs + extra).rstrip() + "\n"
    return text


def _restore_files(before: dict[str, bytes]) -> None:
    for path, blob in before.items():
        with open(path, "wb") as fh:
            fh.write(blob)


def _empty_inplace(before: dict[str, bytes]) -> list[str]:
    emptied = []
    for path, old in before.items():
        with open(path, "rb") as fh:
            new = fh.read()
        if old.strip() and not new.strip():
            emptied.append(path)
    if emptied:
        _restore_files(before)
    return emptied


def _inplace_diffs(before: dict[str, bytes], workspace: str) -> str:
    chunks = []
    for path, old in before.items():
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            new = fh.read()
        old_text = old.decode("utf-8", "replace")
        rel = _rel(path, workspace)
        diff = "".join(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=rel,
            tofile=rel,
        ))
        chunks.append(diff.rstrip() or f"{rel}: no change")
    return "\n".join(chunks)


def _run_argv(argv: list[str], workspace: str) -> tuple[str, int]:
    try:
        proc = subprocess.run(
            argv,
            cwd=os.path.realpath(workspace),
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise WorkspaceError(f"command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceError(f"{argv[0]} timed out after {_CMD_TIMEOUT_S}s") from exc
    parts = []
    if proc.stdout:
        parts.append(proc.stdout.rstrip("\n"))
    if proc.stderr:
        parts.append(proc.stderr.strip())
    if proc.returncode != 0:
        parts.append(f"(exit {proc.returncode})")
    text = "\n".join(p for p in parts if p).strip()
    return (text or "(no output)") + "\n", proc.returncode


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
        r"[._-](Q\d[_A-Za-z0-9]*|IQ\d[_A-Za-z0-9]*|F16|F32|BF16)",
        os.path.basename(path),
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else "?"


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
    include_tiny is set. Deduped by realpath so symlinks and their targets
    don't appear twice. Sorted by basename.
    """
    seen_real = set()   # dedup by resolved inode path
    seen_path = set()   # dedup by literal path string
    out = []
    for root in MODEL_DIRS:
        if not root or not os.path.isdir(root):
            continue
        base_len = len(root.rstrip(os.sep))
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
            depth = dirpath[base_len:].count(os.sep)
            if depth >= 2:
                dirnames[:] = []
            for fn in filenames:
                if not fn.lower().endswith(".gguf"):
                    continue
                full = os.path.join(dirpath, fn)
                if full in seen_path:
                    continue
                real = os.path.realpath(full)
                if real in seen_real:
                    continue   # skip duplicate symlink → same file
                if not include_tiny and is_probably_vocab(full):
                    continue
                seen_path.add(full)
                seen_real.add(real)
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


# ───────────────────────── llama-server sidecar ─────────────────────────
class LlamaServer:
    """Manages a persistent llama-server process.

    Keeps the model loaded in RAM between requests so each query doesn't
    pay the model-load cost (~30-90s for 7B).  Falls back to llama-cli
    if the server binary is missing or the server fails to start.
    """

    _proc: subprocess.Popen | None = None
    _model: str = ""
    _lock = threading.Lock()
    _ready = False

    @classmethod
    def _port_free(cls) -> bool:
        try:
            with socket.create_connection((LLAMA_SERVER_HOST, LLAMA_SERVER_PORT), timeout=0.3):
                return False
        except OSError:
            return True

    @classmethod
    def _wait_ready(cls, timeout: float = 60.0) -> bool:
        """Poll /health until server reports ready or timeout."""
        url = f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    data = json.loads(r.read())
                    if data.get("status") in ("ok", "loading model"):
                        # keep waiting until fully loaded
                        if data.get("status") == "ok":
                            return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    @classmethod
    def start(cls, model_path: str, ctx: int, threads: int) -> bool:
        """Start (or restart) the server for the given model. Returns True on success."""
        if not os.path.exists(LLAMA_SERVER_BIN):
            return False
        with cls._lock:
            # Already running with the right model
            if cls._proc and cls._proc.poll() is None and cls._model == model_path and cls._ready:
                return True
            cls.stop()
            if not cls._port_free():
                # Something else on that port — can't use server mode
                return False
            cmd = [
                LLAMA_SERVER_BIN,
                "-m", model_path,
                "-c", str(ctx),
                "-t", str(threads),
                "-ngl", "0",
                "--host", LLAMA_SERVER_HOST,
                "--port", str(LLAMA_SERVER_PORT),
                "--no-webui",
                "--log-disable",
            ]
            try:
                cls._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                cls._proc = None
                return False
            cls._model = model_path
            cls._ready = False
        # Wait outside the lock so UI thread isn't blocked long
        ok = cls._wait_ready(timeout=120.0)
        with cls._lock:
            cls._ready = ok
        return ok

    @classmethod
    def stop(cls) -> None:
        """Kill the server process if running."""
        if cls._proc:
            try:
                cls._proc.terminate()
                cls._proc.wait(timeout=5)
            except Exception:
                try:
                    cls._proc.kill()
                except Exception:
                    pass
            cls._proc = None
            cls._model = ""
            cls._ready = False

    @classmethod
    def is_ready(cls) -> bool:
        with cls._lock:
            return cls._ready and cls._proc is not None and cls._proc.poll() is None

    @classmethod
    def complete(cls, prompt: str, n_predict: int, stops: list[str],
                 temp: float, top_p: float, repeat_penalty: float,
                 stream_cb=None) -> str:
        """Send a completion request; call stream_cb(chunk_str) as tokens arrive.

        Returns the full generated text, or raises on error.
        """
        url = f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/completion"
        payload = json.dumps({
            "prompt": prompt,
            "n_predict": n_predict,
            "stop": stops,
            "temperature": temp,
            "top_p": top_p,
            "repeat_penalty": repeat_penalty,
            "stream": stream_cb is not None,
            "cache_prompt": True,
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        full = ""
        with urllib.request.urlopen(req, timeout=600) as resp:
            if stream_cb is None:
                data = json.loads(resp.read())
                return data.get("content", "")
            # Streaming: read SSE lines
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    chunk = json.loads(body)
                except Exception:
                    continue
                token = chunk.get("content", "")
                full += token
                if stream_cb:
                    stream_cb(full)
                if chunk.get("stop"):
                    break
        return full


# ───────────────────────── prompt formatting helper ─────────────────────────
def is_deepseek_r1(model_path: str) -> bool:
    """Return True if the model path looks like a DeepSeek-R1 distil."""
    low = model_path.lower()
    return (
        "deepseek-r1" in low
        or "deepseek_r1" in low
        or "r1-distill" in low
        or "r1_distill" in low
    )


def strip_think_blocks(text: str) -> tuple[str, str]:
    """Split DeepSeek-R1 output into (thinking, answer).

    Returns (think_text, answer_text).  If no </think> found, answer is empty
    and all text is treated as still-in-progress thinking.
    """
    if "<think>" not in text and "</think>" not in text:
        return "", text  # not a thinking model output
    # Thinking starts right after <think> (which we pre-primed in the prompt)
    # or at the very start if the model echoed <think> itself.
    body = text
    if body.startswith("<think>"):
        body = body[len("<think>"):]
    if "</think>" in body:
        think_part, _, answer_part = body.partition("</think>")
        return think_part.strip(), answer_part.strip()
    # Still generating inside <think> block
    return body, ""


def format_chat_prompt(model_path: str, history: list, system_prompt: str) -> tuple:
    """Format prompt with the appropriate template depending on the model."""
    low = model_path.lower()
    if is_deepseek_r1(model_path):
        # DeepSeek-R1: ChatML format; we prime <think> so the model reasons first.
        # The final answer appears after </think>. strip_think_blocks() separates them.
        p = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        for r, t in history:
            role = "user" if r == "user" else "assistant"
            p += f"<|im_start|>{role}\n{t}<|im_end|>\n"
        p += "<|im_start|>assistant\n<think>\n"
        marker = "<|im_start|>assistant"
        stops = ["<|im_end|>", "<|im_start|>", "<|endoftext|>", "\n[ Prompt:"]
    elif "qwen" in low or "deepseek" in low:
        # ChatML format (Qwen / other DeepSeek)
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
            "[#a6e3a1]F8[/]  cron        schedule maps scrapes\n"
            "[#a6e3a1]F9[/]  skills      available agent skills\n"
            "[#a6e3a1]F10[/] todo        to-do list\n\n"
            "[bold #f38ba8]commands[/]\n\n"
            "[bold #89b4fa]/agent <goal>[/]          autonomous multi-tab CDP agent (AX/CSS/JEV/HAR)\n"
            "[bold #89b4fa]/fetch <url>[/]           fetch page via CDP or HTTP and inject to chat\n"
            "[bold #89b4fa]/click <target>[/]        click element by index or CSS selector\n"
            "[bold #89b4fa]/type <sel> <text>[/]      type text into input field\n"
            "[bold #89b4fa]/har [start|stop|save][/]  control background network traffic capture\n"
            "[bold #89b4fa]/cdp [port][/]             connect/probe Chrome CDP (9222/9226/9228)\n"
            "[bold #89b4fa]/cron[/]                   open cron job menu (same as F8)\n"
            "[bold #89b4fa]/skills[/]                 list available agent skills (same as F9)\n"
            "[bold #89b4fa]/schedules[/]              view DB schedules & task counts\n"
            "[bold #89b4fa]/todo [add|done|del] …[/]  manage to-do list (same as F10)\n"
            "[bold #89b4fa]/print <path>[/]            show a local file in chat (jsonl pretty)\n"
            "[bold #89b4fa]/runlog[/]                  show latest agent_runs/run_*.jsonl\n"
            "[bold #89b4fa]; read codebase[/]         load cwd source into the chat context\n"
            "[bold #89b4fa]; cat <file>[/]             print a source file (model sees it)\n"
            "[bold #89b4fa]; sed -n '1,80p' <file>[/]  print a line range\n"
            "[bold #89b4fa]; sed -i 's/old/new/g' <f>[/]  edit a file inside the cwd\n"
            "[bold #89b4fa]/sh <cmd>[/]                same commands without the leading ;\n"
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

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """ListView fires this on Enter — use it to trigger the switch."""
        self.action_switch_model()

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
            self.toast("[#f38ba8]no model selected or file missing[/]")
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



# ───────────────────────── skills panel ─────────────────────────
_SKILL_META = {
    "decision": {
        "icon": "🧠",
        "desc": "Parses natural-language goals into structured scrape decisions (query, state, city, fields, cron hint).",
        "status": "core",
    },
    "pincodes": {
        "icon": "📍",
        "desc": "Loads and filters Indian pincode CSV data for geo-targeted scraping tasks.",
        "status": "data",
    },
    "maps_geo": {
        "icon": "🗺",
        "desc": "Executes Google Maps scrapes via CDP browser automation (live) or builds dry-run URL plans.",
        "status": "live/dry",
    },
    "google_workspace": {
        "icon": "📅",
        "desc": "Google Calendar & Sheets integration — exports schedules and scrape results.",
        "status": "optional",
    },
    "gcal_scheduler": {
        "icon": "🗓",
        "desc": "Syncs cron jobs to Google Calendar recurring events.",
        "status": "optional",
    },
}


def _discover_skills() -> list[dict]:
    """Scan agent/skills/ for *.py files and collect metadata."""
    out = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for fn in sorted(os.listdir(SKILLS_DIR)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        path = os.path.join(SKILLS_DIR, fn)
        meta = _SKILL_META.get(name, {})
        # try to load docstring via importlib
        doc = ""
        try:
            spec = importlib.util.spec_from_file_location(f"_skill_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            doc = (inspect.getdoc(mod) or "").split("\n")[0]
        except Exception:
            pass
        # Prefer curated description over auto-docstring
        desc = meta.get("desc") or doc or "(no description)"
        out.append({
            "name": name,
            "file": fn,
            "path": path,
            "icon": meta.get("icon", "⚙"),
            "desc": desc,
            "status": meta.get("status", "available"),
        })
    return out


class SkillsScreen(BaseModal):
    """F9 – display all available agent skills with descriptions."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("r", "rescan", "Rescan"),
        Binding("m", "open_models", "Models"),
        Binding("enter", "activate", "Use / Open"),
    ]

    DEFAULT_CSS = """
    SkillsScreen > Vertical {
        width: 88%;
        max-width: 104;
        height: 80%;
    }
    SkillsScreen #skills-list {
        height: 1fr;
        border: round #313244;
        background: #11111b;
    }
    SkillsScreen #skill-detail {
        height: 6;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "agent skills"
            yield Static(
                "[#89b4fa]↑↓[/] navigate   [#a6e3a1]Enter[/] activate   [#a6e3a1]m[/] switch model   [#a6e3a1]r[/] rescan   [#6c7086]skills auto-chain: decision → pincodes → maps_geo[/]",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="skills-list")
            yield Static(id="skill-detail", markup=True)
            yield Static("Esc / q · m = open model picker (F2)", classes="modal-hint")

    def on_mount(self) -> None:
        self._skills: list[dict] = []
        self._refresh_list()
        self.query_one("#skills-list", ListView).focus()

    # sentinel index 0 is always the "switch model" shortcut
    _MODEL_SENTINEL = {"name": "⟳ switch model", "icon": "📦", "status": "meta",
                       "desc": "Open the model picker (same as F2)", "path": "", "file": ""}

    def _refresh_list(self) -> None:
        lv = self.query_one("#skills-list", ListView)
        lv.clear()
        self._skills = [self._MODEL_SENTINEL] + _discover_skills()
        # Always show model switcher at top
        cur_model = os.path.basename(ModelState.path) if ModelState.path else "none"
        lv.append(ListItem(Label(
            f"📦 [bold]switch model[/]  [#f9e2af]current: {cur_model}[/]  "
            f"[#6c7086]→ open F2 model picker[/]"
        )))
        if len(self._skills) <= 1:
            lv.append(ListItem(Label("[#f38ba8](no skills found in agent/skills/)[/]")))
            return
        for sk in self._skills[1:]:
            icon = sk["icon"]
            status_col = {
                "core": "#a6e3a1",
                "data": "#89b4fa",
                "live/dry": "#f9e2af",
                "optional": "#6c7086",
            }.get(sk["status"], "#cdd6f4")
            label = Label(
                f"{icon} [bold]{sk['name']}[/]  "
                f"[{status_col}]{sk['status']}[/]  "
                f"[#6c7086]{sk['desc'][:60]}[/]"
            )
            lv.append(ListItem(label))

    def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
        self._update_detail()

    def _update_detail(self) -> None:
        lv = self.query_one("#skills-list", ListView)
        box = self.query_one("#skill-detail", Static)
        if lv.index is None or lv.index < 0 or lv.index >= len(self._skills):
            box.update("[#6c7086]no selection[/]")
            return
        sk = self._skills[lv.index]
        # Sentinel: model switcher
        if sk["path"] == "":
            cur_model = ModelState.path or "none"
            box.update(
                f"[bold #89b4fa]action[/]  open model picker (F2)\n"
                f"[bold #89b4fa]current[/] {cur_model}\n"
                f"[#6c7086]Press Enter or m to open the model picker[/]"
            )
            return
        # Check importability
        try:
            spec = importlib.util.spec_from_file_location(f"_chk_{sk['name']}", sk["path"])
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            ok = "[#a6e3a1]✓ importable[/]"
        except Exception as e:
            ok = f"[#f38ba8]✗ import error: {str(e)[:60]}[/]"
        box.update(
            f"[bold #89b4fa]skill[/]   {sk['icon']} {sk['name']}\n"
            f"[bold #89b4fa]file[/]    {sk['file']}\n"
            f"[bold #89b4fa]status[/]  {sk['status']}   {ok}\n"
            f"[bold #89b4fa]desc[/]    {sk['desc']}"
        )

    def action_activate(self) -> None:
        """Enter key: if on the model sentinel, open F2 model picker."""
        lv = self.query_one("#skills-list", ListView)
        if lv.index is not None and lv.index < len(self._skills):
            if self._skills[lv.index]["path"] == "":
                self.action_open_models()

    def action_open_models(self) -> None:
        """Open the F2 model picker from within the Skills panel."""
        self.dismiss(None)
        self.app.push_screen(ModelScreen())

    def action_rescan(self) -> None:
        self._refresh_list()
        self._update_detail()
        self.toast("skills rescanned")


# ───────────────────────── schedules panel ─────────────────────────
class SchedulesScreen(BaseModal):
    """View-only panel showing DB schedules and recent task counts."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("r", "refresh_data", "Refresh"),
    ]

    DEFAULT_CSS = """
    SchedulesScreen > Vertical {
        width: 92%;
        max-width: 108;
        height: 80%;
    }
    SchedulesScreen #sched-list {
        height: 1fr;
        border: round #313244;
        background: #11111b;
    }
    SchedulesScreen #sched-stats {
        height: 6;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "schedules & task queue"
            yield Static(
                "[#89b4fa]↑↓[/] navigate   [#a6e3a1]r[/] refresh   [#6c7086]edit via /cron or F8[/]",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="sched-list")
            yield Static(id="sched-stats", markup=True)
            yield Static("Esc / q to close · r to refresh", classes="modal-hint")

    def on_mount(self) -> None:
        self.action_refresh_data()

    def _get_db(self):
        try:
            from agent.config import AgentConfig
            from agent.database import Database
            cfg = AgentConfig()
            return Database(cfg.db_path)
        except Exception:
            return None

    def action_refresh_data(self) -> None:
        lv = self.query_one("#sched-list", ListView)
        lv.clear()
        db = self._get_db()
        if db is None:
            lv.append(ListItem(Label("[#f38ba8](database not available)[/]")))
            return

        schedules = db.get_schedules()
        if not schedules:
            lv.append(ListItem(Label("[#6c7086](no schedules — use F8 / /cron to add)[/]")))
        else:
            for s in schedules:
                en = "[#a6e3a1]ON [/]" if s.get("enabled") else "[#6c7086]OFF[/]"
                name = (s.get("name") or "?")[:24]
                expr = s.get("cron_expr", "?")
                next_r = (s.get("next_run_at") or "?")[:16]
                last_r = (s.get("last_run_at") or "—")[:16]
                tt = s.get("task_type", "?")
                label = (
                    f"{en} [bold]{name}[/]  [#89b4fa]{expr}[/]  "
                    f"next [#a6e3a1]{next_r}[/]  last [#6c7086]{last_r}[/]  "
                    f"[#45475a]{tt}[/]"
                )
                lv.append(ListItem(Label(label)))

        # Task counts
        try:
            counts = db.count_tasks_by_status()
            places = db.count_places()
        except Exception:
            counts, places = {}, {}

        total_tasks = sum(counts.values())
        pending = counts.get("pending", 0)
        running = counts.get("running", 0)
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)

        stats_text = (
            f"[bold #f9e2af]task queue[/]  "
            f"total [bold]{total_tasks}[/]  "
            f"pending [#89b4fa]{pending}[/]  "
            f"running [#a6e3a1]{running}[/]  "
            f"done [#6c7086]{completed}[/]  "
            f"failed [#f38ba8]{failed}[/]\n"
            f"[bold #f9e2af]places db[/]  "
            f"total [bold]{places.get('total', 0)}[/]  "
            f"with phone [#a6e3a1]{places.get('with_phone', 0)}[/]\n"
            f"[#6c7086]Edit schedules via /cron (F8) · add tasks via /agent <goal>[/]"
        )
        try:
            self.query_one("#sched-stats", Static).update(stats_text)
        except Exception:
            pass


# ───────────────────────── to-do list panel ─────────────────────────
def _load_todos() -> list[dict]:
    """Load to-do items from JSON file."""
    try:
        if os.path.exists(TODO_PATH):
            with open(TODO_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_todos(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(TODO_PATH), exist_ok=True)
    with open(TODO_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


class TodoScreen(BaseModal):
    """F10 – persistent to-do list (saved to ~/.llama-tui/todo.json)."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
        Binding("a", "add_item", "Add"),
        Binding("d", "done_item", "Done"),
        Binding("x", "delete_item", "Delete"),
        Binding("r", "refresh_list", "Refresh"),
    ]

    DEFAULT_CSS = """
    TodoScreen > Vertical {
        width: 80%;
        max-width: 96;
        height: 80%;
    }
    TodoScreen #todo-list {
        height: 1fr;
        border: round #313244;
        background: #11111b;
    }
    TodoScreen #todo-input {
        margin: 0 0 1 0;
        border: round #313244;
        background: #11111b;
    }
    TodoScreen #todo-input:focus {
        border: round #89b4fa;
    }
    TodoScreen #todo-status {
        height: 2;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical() as v:
            v.border_title = "to-do list"
            yield Static(
                "[#89b4fa]a[/] add   [#a6e3a1]d[/] mark done   [#f38ba8]x[/] delete   [#6c7086]r[/] refresh",
                markup=True,
                classes="modal-section",
            )
            yield ListView(id="todo-list")
            yield Input(placeholder="new task — type here and press 'a' or Enter…", id="todo-input")
            yield Static(id="todo-status", markup=True)
            yield Static(
                f"Saved to {TODO_PATH}  ·  Esc / q to close",
                classes="modal-hint",
            )

    def on_mount(self) -> None:
        self._items: list[dict] = _load_todos()
        self._refresh_list()
        self.query_one("#todo-list", ListView).focus()

    def _refresh_list(self) -> None:
        lv = self.query_one("#todo-list", ListView)
        lv.clear()
        if not self._items:
            lv.append(ListItem(Label("[#6c7086](empty — press 'a' to add a task)[/]")))
        else:
            for i, item in enumerate(self._items):
                done = bool(item.get("done"))
                created = (item.get("created_at") or "")[:10]
                text = item.get("text", "?")
                check = "[#a6e3a1]✓[/]" if done else "[#6c7086]○[/]"
                style = "#6c7086" if done else "#cdd6f4"
                label = (
                    f"{check} [{style}]{text}[/]"
                    + (f"  [#45475a]{created}[/]" if created else "")
                )
                lv.append(ListItem(Label(label)))
        done_count = sum(1 for it in self._items if it.get("done"))
        total = len(self._items)
        try:
            self.query_one("#todo-status", Static).update(
                f"[#6c7086]{done_count}/{total} done  ·  "
                f"{total - done_count} remaining[/]"
            )
        except Exception:
            pass

    def _selected_index(self) -> int | None:
        lv = self.query_one("#todo-list", ListView)
        if lv.index is None or lv.index < 0 or not self._items:
            return None
        if lv.index >= len(self._items):
            return None
        return lv.index

    def _get_input_text(self) -> str:
        try:
            return self.query_one("#todo-input", Input).value.strip()
        except Exception:
            return ""

    def _clear_input(self) -> None:
        try:
            self.query_one("#todo-input", Input).value = ""
        except Exception:
            pass

    def action_add_item(self) -> None:
        text = self._get_input_text()
        if not text:
            self.query_one("#todo-input", Input).focus()
            return
        self._items.append({
            "text": text,
            "done": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        _save_todos(self._items)
        self._clear_input()
        self._refresh_list()
        self.toast(f"added: {text[:40]}")

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.action_add_item()

    def action_done_item(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self._items[idx]["done"] = not self._items[idx].get("done", False)
        _save_todos(self._items)
        self._refresh_list()
        state = "done" if self._items[idx]["done"] else "undone"
        self.toast(f"marked {state}: {self._items[idx].get('text', '')[:40]}")

    def action_delete_item(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        text = self._items[idx].get("text", "?")[:40]
        self._items.pop(idx)
        _save_todos(self._items)
        self._refresh_list()
        self.toast(f"deleted: {text}")

    def action_refresh_list(self) -> None:
        self._items = _load_todos()
        self._refresh_list()
        self.toast("to-do list refreshed")


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
        Binding("f9", "panel_skills", "Skills"),
        Binding("f10", "panel_todo", "Todo"),
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
                    placeholder="message · /help · ; read codebase · ; cat file · ; sed …",
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
        self.workspace = os.path.abspath(os.getcwd())
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
        # Escape Rich markup-special chars so model output (e.g. <think>) renders literally
        safe = text.replace("[", "\\[").replace("<", "\\<")
        if role == "user":
            t.append("▌you  ", style=f"bold {C_USER}")
            t.append(safe, style=C_TEXT)
        elif role == "ai":
            t.append("▌ai   ", style=f"bold {C_AI}")
            t.append(safe, style=C_TEXT)
            if cursor:
                t.append("█", style=C_AI)
        else:
            t.append(safe, style=f"italic {C_DIM}")
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
        workspace = getattr(self, "workspace", None) or os.getcwd()
        if classify_workspace_input(msg, workspace):
            event.input.value = ""
            self.handle_workspace_input(msg)
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
            "skills": self.action_panel_skills,
            "schedules": self.action_panel_schedules,
            "todo": self.action_panel_todo,
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
        elif cmd == "todo":
            self._handle_todo_cmd(arg)
        elif cmd == "schedules":
            self.action_panel_schedules()
        elif cmd == "skills":
            self.action_panel_skills()
        elif cmd in ("code", "codebase"):
            self.handle_workspace_input("; read codebase of the current directory")
        elif cmd == "sh":
            if not arg.strip():
                self.add_message(
                    "sys",
                    "Usage: /sh cat <file>  ·  /sh sed -n '1,40p' <file>  ·  ; read codebase",
                )
            else:
                self.handle_workspace_input("; " + arg.strip())
        elif cmd == "cat":
            if not arg.strip():
                self.add_message("sys", "Usage: /cat <file>  ·  ; cat <file>  ·  ; read codebase")
            else:
                self.handle_workspace_input("; cat " + arg.strip())
        elif cmd in ("print", "show", "runlog"):
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
            # DeepSeek-R1 needs much larger context/prediction budget for reasoning
            _is_r1 = is_deepseek_r1(model_path)
            _n_predict = _DS_R1_N_PREDICT if _is_r1 else N_PREDICT
            _ctx = _DS_R1_CTX if _is_r1 else CTX
            _timeout = _DS_R1_TIMEOUT if _is_r1 else TIMEOUT_S
            if _is_r1:
                ui(self.log_line, f"[#f9e2af]DeepSeek-R1: ctx={_ctx} n_predict={_n_predict} — reasoning mode[/]")
            cmd = [
                LLAMA_BIN, "-m", model_path, "-f", prompt_path,
                "-n", str(_n_predict), "-t", str(THREADS), "-c", str(_ctx),
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
                timeout=_timeout,
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
            gen = gen.strip()
            # For DeepSeek-R1, extract only the answer after </think>
            if _is_r1:
                _, answer = strip_think_blocks(gen)
                gen = answer if answer else gen
            return gen
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

    def handle_workspace_input(self, msg: str) -> None:
        """Run ; cat / ; sed / ; read codebase and keep the output in chat context."""
        if self.busy:
            self.log_line(f"[{C_WARN}]busy — Ctrl+X to stop[/]")
            return
        workspace = getattr(self, "workspace", None) or os.getcwd()
        self.add_message("user", msg)
        try:
            result = run_workspace_line(msg, workspace)
        except WorkspaceError as exc:
            self.add_message("sys", f"⚠️ {exc}")
            self.history.append(("user", msg))
            self.history.append(("assistant", f"Workspace error: {exc}"))
            self.log_line(f"[{C_WARN}]workspace:[/] {exc}")
            return
        display = result
        if len(display) > WORKSPACE_DISPLAY_CHARS:
            display = display[:WORKSPACE_DISPLAY_CHARS] + "\n… (display truncated)"
        self.add_message("sys", display.rstrip())
        hist = result
        if len(hist) > WORKSPACE_HISTORY_CHARS:
            hist = hist[:WORKSPACE_HISTORY_CHARS] + (
                "\n… (truncated for context — ; cat <file> or ; sed -n 'A,Bp' <file>)"
            )
        self.history.append(("user", msg))
        self.history.append(("assistant", hist.rstrip()))
        self.turns += 1
        self.log_line(f"[#a6e3a1]workspace[/] {msg[:80]}")

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


    def _handle_todo_cmd(self, arg: str) -> None:
        """Handle /todo [add <text>|done <n>|del <n>|list] from chat input."""
        parts = (arg or "").strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""

        items = _load_todos()

        if sub in ("", "list", "ls"):
            if not items:
                self.add_message("sys", "📋 To-do list is empty.  Use /todo add <task> to add one.")
                return
            lines = ["📋 [bold]To-do list[/bold]"]
            for i, it in enumerate(items, 1):
                done = it.get("done", False)
                check = "✓" if done else "○"
                text = it.get("text", "?")
                lines.append(f"  {i}. {check} {text}")
            self.add_message("sys", "\n".join(lines))

        elif sub == "add":
            if not rest:
                self.log_line(f"[{C_WARN}]Usage: /todo add <task text>[/]")
                return
            items.append({"text": rest, "done": False, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            _save_todos(items)
            self.add_message("sys", f"📋 Added: {rest}")
            self.log_line(f"todo added: {rest[:40]}")

        elif sub in ("done", "check"):
            try:
                n = int(rest) - 1
                if 0 <= n < len(items):
                    items[n]["done"] = True
                    _save_todos(items)
                    self.add_message("sys", f"📋 ✓ Done: {items[n].get('text', '')}")
                else:
                    self.log_line(f"[{C_WARN}]todo: index {n+1} out of range[/]")
            except ValueError:
                self.log_line(f"[{C_WARN}]Usage: /todo done <number>[/]")

        elif sub in ("del", "delete", "rm", "remove"):
            try:
                n = int(rest) - 1
                if 0 <= n < len(items):
                    text = items[n].get("text", "?")
                    items.pop(n)
                    _save_todos(items)
                    self.add_message("sys", f"📋 Deleted: {text}")
                else:
                    self.log_line(f"[{C_WARN}]todo: index {n+1} out of range[/]")
            except ValueError:
                self.log_line(f"[{C_WARN}]Usage: /todo del <number>[/]")

        elif sub in ("clear", "reset"):
            # Only clear completed items
            before = len(items)
            items = [it for it in items if not it.get("done")]
            _save_todos(items)
            removed = before - len(items)
            self.add_message("sys", f"📋 Cleared {removed} completed task(s). {len(items)} remaining.")

        elif sub in ("open", "show"):
            self.action_panel_todo()
        else:
            self.log_line(f"[{C_WARN}]todo: unknown subcommand '{sub}' — try add/done/del/list/clear[/]")

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

    def action_panel_skills(self) -> None:
        self.push_screen(SkillsScreen())

    def action_panel_todo(self) -> None:
        self.push_screen(TodoScreen())

    def action_panel_schedules(self) -> None:
        self.push_screen(SchedulesScreen())

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
        # Pre-warm llama-server in background so first reply is fast
        if os.path.exists(LLAMA_SERVER_BIN):
            _is_r1 = is_deepseek_r1(new_path)
            _ctx = _DS_R1_CTX if _is_r1 else CTX
            self.log_line(f"[#6c7086]starting llama-server on :{LLAMA_SERVER_PORT}…[/]")
            def _start_server():
                ok = LlamaServer.start(new_path, ctx=_ctx, threads=THREADS)
                status = f"[#a6e3a1]llama-server ready[/]" if ok else f"[{C_WARN}]llama-server failed — using llama-cli fallback[/]"
                self.call_from_thread(self.log_line, status)
            threading.Thread(target=_start_server, daemon=True).start()

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
        model_path = ModelState.path
        _, marker, stops = format_chat_prompt(model_path, [], "")
        _is_r1 = is_deepseek_r1(model_path)
        _n_predict = _DS_R1_N_PREDICT if _is_r1 else N_PREDICT
        _ctx = _DS_R1_CTX if _is_r1 else CTX
        _timeout = _DS_R1_TIMEOUT if _is_r1 else TIMEOUT_S

        # ── helper: display text during streaming ──
        def _show(content: str) -> None:
            if _is_r1:
                think_text, answer_text = strip_think_blocks(content.lstrip())
                if answer_text:
                    shown = answer_text
                elif think_text:
                    lines = think_text.strip().splitlines()
                    last_line = lines[-1][:80] if lines else ""
                    shown = f"💭 thinking… {last_line}"
                else:
                    shown = content.lstrip()
            else:
                shown = content.lstrip()
            ui(self._update_live, shown, True)

        # ── try llama-server path first ──
        if LlamaServer.is_ready() and LlamaServer._model == model_path:
            try:
                ui(self.log_line, "sending to llama-server…")
                self.state = "generating"
                self.gen_start = time.time()
                last_ui = 0.0

                def _stream_cb(full_so_far: str) -> None:
                    nonlocal last_ui
                    self.gen_tokens += 1
                    now = time.time()
                    if now - last_ui > 0.08:
                        last_ui = now
                        _show(full_so_far)

                raw_reply = LlamaServer.complete(
                    prompt=prompt,
                    n_predict=_n_predict,
                    stops=stops,
                    temp=TEMP,
                    top_p=TOP_P,
                    repeat_penalty=REPEAT_PENALTY,
                    stream_cb=_stream_cb,
                )
                if _is_r1:
                    _, answer = strip_think_blocks(raw_reply)
                    reply = answer if answer else raw_reply
                else:
                    reply = raw_reply.strip()
                if not reply and self.stop_flag:
                    reply = "[stopped]"
                elif not reply:
                    reply = "[empty response from server]"
                ui(self._finish, reply, "", time.time() - t0)
                return
            except Exception as e:
                ui(self.log_line, f"[{C_WARN}]server error ({e}) — falling back to llama-cli[/]")
                self.state = "loading"

        # ── llama-cli fallback ──
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, dir=HOME, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_path = f.name

            flags = llama_flags()
            if _is_r1:
                ui(self.log_line, f"[#f9e2af]DeepSeek-R1: ctx={_ctx} n_predict={_n_predict} — reasoning mode[/]")
            cmd = [
                LLAMA_BIN, "-m", model_path, "-f", prompt_path,
                "-n", str(_n_predict), "-t", str(THREADS), "-c", str(_ctx),
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
                if time.time() - t0 > _timeout:
                    self.proc.kill()
                    ui(self.log_line, f"[{C_ERR}]timeout after {_timeout}s[/]")
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
                    _show(reply)
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
                if _is_r1:
                    _, answer = strip_think_blocks(reply)
                    reply = answer if answer else reply
            else:
                reply = ""
            stderr_text = b"".join(err_chunks).decode("utf-8", "replace")

            if not reply:
                if self.stop_flag:
                    reply = "[stopped]"
                else:
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
            ui(self._finish, f"[Error: llama binary not found at {LLAMA_BIN}]", "", time.time() - t0, True)
        except PermissionError:
            ui(self._finish, f"[Error: llama binary not executable: {LLAMA_BIN}]", "", time.time() - t0, True)
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
