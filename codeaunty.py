#!/usr/bin/env python3
"""
codeuncle.py - Clean Python code structure visualizer with line numbers
               + lexical/text analysis layer (comments, TODOs, docstrings,
                 embedded strings, print/input/bare-except density, URLs)
               + interactive/presentation call detection (Prompt.ask,
                 Confirm.ask, Console.print, logging.*, etc.)
               + string preview of what each call actually says

Usage:
  python codeuncle.py <filename.py> [--snippets] [--no-lexical]
  python codeuncle.py <filename.py> --callgraph [--graph-format text|mermaid|dot]
                                     [--internal-only] [--output FILE]
  python codeuncle.py <filename.py> --stats        # only lexical summary
  python codeuncle.py <filename.py> --comments     # only comment list
  python codeuncle.py <filename.py> --todos        # only TODO/FIXME/etc.
  python codeuncle.py <filename.py> --interactive  # interactive/presentation with strings
  python codeuncle.py <filename.py> --ui           # UI flow: only presentation/interactive, grouped by function
"""

import ast
import io
import os
import re
import sys
import tokenize
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ============================================
# COLOR CODES
# ============================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GRAY = '\033[90m'
    MAGENTA = '\033[95m'

# ============================================
# SOURCE CODE CACHE
# ============================================
class SourceCache:
    """Cache source code lines for reference"""
    def __init__(self, source_lines: List[str]):
        self.lines = source_lines

    def get_snippet(self, start_line: int, end_line: int = None, context: int = 0) -> str:
        if end_line is None:
            end_line = start_line

        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.lines), end_line)

        if context > 0:
            start_idx = max(0, start_idx - context)
            end_idx = min(len(self.lines), end_idx + context)

        snippet_lines = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line = self.lines[i].rstrip()
            if line_num == start_line:
                snippet_lines.append(f"{Colors.YELLOW}{line_num:4d} \u2192 {line}{Colors.END}")
            elif line_num == end_line and start_line != end_line:
                snippet_lines.append(f"{Colors.GREEN}{line_num:4d} \u2192 {line}{Colors.END}")
            else:
                snippet_lines.append(f"{Colors.GRAY}{line_num:4d}   {line}{Colors.END}")

        return '\n'.join(snippet_lines)

# ============================================
# LEXICAL REPORT (dataclass + rendering)
# ============================================
# Call records are (lineno, qualified_name, preview_string, enclosing_scope)
CallRecord = Tuple[int, str, str, str]

@dataclass
class LexicalReport:
    total_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    code_lines: int = 0
    max_line_len: int = 0
    max_line_no: int = 0
    uses_tabs: bool = False
    indent_is_spaces: bool = True
    shebang: Optional[str] = None
    encoding: Optional[str] = None
    comments: List[Tuple[int, str]] = field(default_factory=list)
    markers: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    docstrings: Set[int] = field(default_factory=set)
    long_strings: List[Tuple[int, int, int]] = field(default_factory=list)
    print_calls: List[int] = field(default_factory=list)
    input_calls: List[int] = field(default_factory=list)
    bare_excepts: List[int] = field(default_factory=list)
    urls: List[Tuple[int, str]] = field(default_factory=list)
    noqa_lines: List[int] = field(default_factory=list)
    type_comment_lines: List[int] = field(default_factory=list)
    # (lineno, name, preview, enclosing_function)
    interactive_calls: List[CallRecord] = field(default_factory=list)
    presentation_calls: List[CallRecord] = field(default_factory=list)
    tokenize_error: Optional[str] = None

    def comment_ratio(self) -> float:
        denom = self.code_lines + self.comment_lines
        return (self.comment_lines / denom * 100.0) if denom else 0.0

    def docstring_coverage(self, total_defs: int) -> Tuple[int, float]:
        have = len(self.docstrings)
        pct = (have / total_defs * 100.0) if total_defs else 0.0
        return have, pct

    # --- Rendering -------------------------------------------------------
    def render_summary(self) -> List[str]:
        r = self
        lines = [f"{Colors.BOLD}{Colors.HEADER}\U0001f4dd Lexical Analysis{Colors.END}"]

        if r.shebang:
            lines.append(f"   Shebang:  {Colors.CYAN}{r.shebang}{Colors.END}")
        if r.encoding:
            lines.append(f"   Encoding: {Colors.CYAN}{r.encoding}{Colors.END}")

        indent = "spaces" if r.indent_is_spaces else f"{Colors.YELLOW}tabs{Colors.END}"
        lines.append(
            f"   Lines: {r.total_lines} total | {r.blank_lines} blank | "
            f"{r.comment_lines} comment | {r.code_lines} code"
        )
        lines.append(
            f"   Comment ratio: {r.comment_ratio():.1f}%  |  "
            f"Max line: {r.max_line_len} chars (L{r.max_line_no})  |  Indent: {indent}"
        )

        if r.markers:
            parts = [f"{w}\u00d7{len(v)}" for w, v in sorted(r.markers.items())]
            lines.append(f"   Markers: {Colors.YELLOW}{', '.join(parts)}{Colors.END}")

        if r.long_strings:
            lines.append(
                f"   Multi-line strings: {Colors.CYAN}{len(r.long_strings)}{Colors.END} "
                f"(likely embedded JS/HTML/SQL)"
            )

        lines.append(
            f"   print() calls: {len(r.print_calls)}  |  "
            f"input() calls: {len(r.input_calls)}  |  "
            f"bare except: {len(r.bare_excepts)}"
        )

        # Interactive calls with preview strings
        if r.interactive_calls:
            lines.append(
                f"   {Colors.YELLOW}\u2328\ufe0f  Interactive (blocks on input): "
                f"{len(r.interactive_calls)}{Colors.END}"
            )
            for ln, name, preview, _scope in r.interactive_calls[:5]:
                snippet = f"  {Colors.GRAY}\"{preview}\"{Colors.END}" if preview else ""
                lines.append(f"      {Colors.GRAY}L{ln}: {name}{Colors.END}{snippet}")
            if len(r.interactive_calls) > 5:
                lines.append(f"      {Colors.DIM}... and {len(r.interactive_calls) - 5} more{Colors.END}")

        # Presentation calls with preview strings
        if r.presentation_calls:
            lines.append(
                f"   {Colors.CYAN}\U0001f5a8\ufe0f  Presentation (writes to stdout): "
                f"{len(r.presentation_calls)}{Colors.END}"
            )
            for ln, name, preview, _scope in r.presentation_calls[:5]:
                snippet = f"  {Colors.GRAY}\"{preview}\"{Colors.END}" if preview else ""
                lines.append(f"      {Colors.GRAY}L{ln}: {name}{Colors.END}{snippet}")
            if len(r.presentation_calls) > 5:
                lines.append(f"      {Colors.DIM}... and {len(r.presentation_calls) - 5} more{Colors.END}")

        if r.urls:
            lines.append(f"   Hardcoded URLs: {Colors.CYAN}{len(r.urls)}{Colors.END}")

        if r.noqa_lines:
            lines.append(f"   # noqa: {len(r.noqa_lines)} line(s)")
        if r.type_comment_lines:
            lines.append(f"   # type: comments: {len(r.type_comment_lines)}")

        if r.tokenize_error:
            lines.append(f"   {Colors.RED}tokenize warning: {r.tokenize_error}{Colors.END}")

        return lines

    def render_comments(self, limit: int = 100) -> List[str]:
        out = [f"{Colors.BOLD}{Colors.HEADER}\U0001f4ac Comments ({len(self.comments)}){Colors.END}"]
        for ln, text in self.comments[:limit]:
            out.append(f"   {Colors.GRAY}L{ln:4d}{Colors.END}  {text}")
        if len(self.comments) > limit:
            out.append(f"   {Colors.DIM}... and {len(self.comments) - limit} more{Colors.END}")
        return out

    def render_markers(self) -> List[str]:
        if not self.markers:
            return [f"{Colors.GREEN}\u2705 No TODO/FIXME/HACK markers found{Colors.END}"]
        out = [f"{Colors.BOLD}{Colors.HEADER}\u26a0\ufe0f  Markers{Colors.END}"]
        for word, line_nos in sorted(self.markers.items()):
            out.append(f"   {Colors.YELLOW}{word}{Colors.END} x{len(line_nos)}: "
                       f"L{', L'.join(str(x) for x in line_nos)}")
        return out

    def render_interactive(self) -> List[str]:
        """Render interactive + presentation calls with their literal strings."""
        out = []
        if self.interactive_calls:
            out.append(f"{Colors.BOLD}{Colors.HEADER}\u2328\ufe0f  Interactive Calls "
                       f"({len(self.interactive_calls)}){Colors.END}")
            out.append(f"   {Colors.DIM}These block on user input — cannot run from cron/CI/pipe{Colors.END}")
            for ln, name, preview, scope in self.interactive_calls:
                line = f"   {Colors.YELLOW}L{ln:4d}{Colors.END}  {Colors.CYAN}{name}{Colors.END}"
                if scope:
                    line += f" {Colors.DIM}({scope}){Colors.END}"
                if preview:
                    line += f"  {Colors.GRAY}\"{preview}\"{Colors.END}"
                out.append(line)
        else:
            out.append(f"{Colors.GREEN}\u2705 No interactive calls found{Colors.END}")

        out.append("")
        if self.presentation_calls:
            out.append(f"{Colors.BOLD}{Colors.HEADER}\U0001f5a8\ufe0f  Presentation Calls "
                       f"({len(self.presentation_calls)}){Colors.END}")
            out.append(f"   {Colors.DIM}These write to stdout — mixed logic + presentation{Colors.END}")
            for ln, name, preview, scope in self.presentation_calls:
                line = f"   {Colors.GRAY}L{ln:4d}{Colors.END}  {Colors.CYAN}{name}{Colors.END}"
                if scope:
                    line += f" {Colors.DIM}({scope}){Colors.END}"
                if preview:
                    line += f"  {Colors.DIM}\"{preview}\"{Colors.END}"
                out.append(line)
        else:
            out.append(f"{Colors.GREEN}\u2705 No presentation calls found{Colors.END}")

        return out

    def render_ui_flow(self) -> List[str]:
        """
        Group presentation/interactive calls by enclosing function, in line order.
        This is the "read the UI top to bottom" view.
        """
        # Merge all UI calls
        all_calls: List[CallRecord] = []
        for rec in self.interactive_calls:
            all_calls.append(rec)
        for rec in self.presentation_calls:
            all_calls.append(rec)

        if not all_calls:
            return [f"{Colors.GREEN}\u2705 No UI calls found{Colors.END}"]

        # Group by enclosing scope
        by_scope: Dict[str, List[CallRecord]] = defaultdict(list)
        for rec in all_calls:
            scope = rec[3] or "<module>"
            by_scope[scope].append(rec)

        out = [f"{Colors.BOLD}{Colors.HEADER}\U0001f3ad UI Flow{Colors.END}"]
        out.append(f"   {Colors.DIM}Presentation & interactive calls, grouped by function, in line order{Colors.END}")

        interactive_set = {(ln, name) for ln, name, _, _ in self.interactive_calls}

        for scope in sorted(by_scope, key=lambda s: min(r[0] for r in by_scope[s])):
            calls = sorted(by_scope[scope], key=lambda r: r[0])
            out.append("")
            out.append(f"   {Colors.BOLD}{Colors.MAGENTA}{scope}{Colors.END}")
            for ln, name, preview, _ in calls:
                is_interactive = (ln, name) in interactive_set
                icon = "\u2328\ufe0f " if is_interactive else "\U0001f5a8\ufe0f "
                color = Colors.YELLOW if is_interactive else Colors.CYAN
                line = f"      {Colors.GRAY}L{ln:4d}{Colors.END}  {icon}{color}{name}{Colors.END}"
                if preview:
                    line += f"  {Colors.DIM}\"{preview}\"{Colors.END}"
                out.append(line)

        return out

# ============================================
# LEXICAL ANALYZER
# ============================================
MARKER_WORDS = ("TODO", "FIXME", "HACK", "XXX", "NOTE", "BUG", "WIP", "OPTIMIZE")
URL_RE = re.compile(r"https?://[^\s'\"<>\)]+")
SHEBANG_RE = re.compile(r"^#!\s*(\S+)")
ENCODING_RE = re.compile(r"coding[:=]\s*([-\w.]+)")
NOQA_RE = re.compile(r"#\s*noqa\b", re.I)
TYPE_COMMENT_RE = re.compile(r"#\s*type:\s*", re.I)

# --- Interactive / presentation function names ---------------------------
INTERACTIVE_FUNCS = {
    "input",
    "Prompt.ask", "Confirm.ask", "IntPrompt.ask", "FloatPrompt.ask",
    "click.prompt", "click.confirm", "typer.prompt", "typer.confirm",
    "getpass.getpass",
}

PRESENTATION_FUNCS = {
    "print",
    "Console.print",
    "console.print",
    "pprint.pprint",
    "sys.stdout.write",
    "sys.stderr.write",
    "logging.info", "logging.warning", "logging.error", "logging.debug",
    "logger.info", "logger.warning", "logger.error", "logger.debug",
}

_INTERACTIVE_SUFFIXES = (".ask", ".prompt", ".confirm")
_PRESENTATION_SUFFIXES = (".print", ".write", ".info", ".warning", ".error", ".debug")


class LexicalAnalyzer:
    """
    Text-level analysis that runs alongside the AST. Catches things AST
    throws away: comments, TODO markers, shebang/encoding, embedded
    multi-line strings, raw print/input density, bare excepts, URLs,
    and interactive/presentation call sites (with literal-string previews).
    """

    def __init__(self, source_lines: List[str], filename: str = "<unknown>"):
        self.source_lines = source_lines
        self.filename = filename
        self.report = LexicalReport()

    def analyze(self, tree: Optional[ast.AST] = None) -> LexicalReport:
        self._line_stats()
        self._tokenize_pass()
        if tree is not None:
            self._ast_pass(tree)
        else:
            try:
                tree = ast.parse(''.join(self.source_lines), filename=self.filename)
                self._ast_pass(tree)
            except SyntaxError:
                pass
        return self.report

    # --- Pass 1: raw line stats ------------------------------------------
    def _line_stats(self):
        r = self.report
        r.total_lines = len(self.source_lines)

        for i, line in enumerate(self.source_lines, 1):
            raw = line.rstrip("\n")
            length = len(raw)
            if length > r.max_line_len:
                r.max_line_len = length
                r.max_line_no = i

            leading = raw[:len(raw) - len(raw.lstrip())]
            if "\t" in leading:
                r.uses_tabs = True
                r.indent_is_spaces = False

            stripped = raw.strip()
            if not stripped:
                r.blank_lines += 1
            elif stripped.startswith("#"):
                r.comment_lines += 1
                r.comments.append((i, stripped))
            else:
                r.code_lines += 1

        if self.source_lines:
            m = SHEBANG_RE.match(self.source_lines[0])
            if m:
                r.shebang = self.source_lines[0].strip()
        head = "".join(self.source_lines[:2])
        enc = ENCODING_RE.search(head)
        if enc:
            r.encoding = enc.group(1)

    # --- Pass 2: tokenize pass (comments & multi-line strings) -----------
    def _tokenize_pass(self):
        r = self.report
        src = ''.join(self.source_lines)
        reader = io.StringIO(src).readline
        seen_comment_lines = {ln for ln, _ in r.comments}

        try:
            for tok in tokenize.generate_tokens(reader):
                ttype = tok.type
                tstr = tok.string

                if ttype == tokenize.COMMENT:
                    line_no = tok.start[0]
                    if line_no not in seen_comment_lines:
                        r.comments.append((line_no, tstr))
                        seen_comment_lines.add(line_no)

                    up = tstr.upper()
                    for w in MARKER_WORDS:
                        if re.search(rf"\b{w}\b", up):
                            r.markers[w].append(line_no)

                    if NOQA_RE.search(tstr):
                        r.noqa_lines.append(line_no)
                    if TYPE_COMMENT_RE.search(tstr):
                        r.type_comment_lines.append(line_no)

                elif ttype == tokenize.STRING:
                    start_ln = tok.start[0]
                    end_ln = tok.end[0]
                    if end_ln > start_ln:
                        r.long_strings.append((start_ln, end_ln, len(tstr)))

                    for m in URL_RE.finditer(tstr):
                        r.urls.append((start_ln, m.group(0)))

        except tokenize.TokenError as e:
            r.tokenize_error = str(e)
        except IndentationError as e:
            r.tokenize_error = f"IndentationError: {e}"

    # --- Pass 3: AST pass for docstrings / calls / bare except -----------
    def _ast_pass(self, tree: ast.AST):
        r = self.report

        # Compute enclosing scope for every node once. We walk the tree
        # manually so we can track class/function context for each call.
        scope_map: Dict[int, str] = {}
        self._build_scope_map(tree, class_stack=[], scope_stack=[], scope_map=scope_map)

        scope_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)

        for node in ast.walk(tree):
            if isinstance(node, scope_types):
                if ast.get_docstring(node) is not None:
                    r.docstrings.add(getattr(node, "lineno", 0))

            if isinstance(node, ast.Call):
                name = self._resolve_call_name(node)
                if name is None:
                    continue

                if name == "print":
                    r.print_calls.append(node.lineno)
                elif name == "input":
                    r.input_calls.append(node.lineno)

                scope = scope_map.get(id(node), "")

                if self._is_interactive(name):
                    preview = self._extract_call_literal(node)
                    r.interactive_calls.append((node.lineno, name, preview, scope))

                if self._is_presentation(name):
                    preview = self._extract_call_literal(node)
                    r.presentation_calls.append((node.lineno, name, preview, scope))

            if isinstance(node, ast.ExceptHandler) and node.type is None:
                r.bare_excepts.append(getattr(node, "lineno", 0))

    def _build_scope_map(self, node: ast.AST, class_stack: List[str],
                         scope_stack: List[str], scope_map: Dict[int, str]):
        """Tag every node with its enclosing qualified scope name."""
        is_class = isinstance(node, ast.ClassDef)
        is_func = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))

        if is_class:
            class_stack.append(node.name)
        if is_func:
            if class_stack:
                qualified = f"{class_stack[-1]}.{node.name}"
            else:
                qualified = node.name
            scope_stack.append(qualified)

        current_scope = scope_stack[-1] if scope_stack else ""

        for child in ast.iter_child_nodes(node):
            scope_map[id(child)] = current_scope
            self._build_scope_map(child, class_stack, scope_stack, scope_map)

        if is_func:
            scope_stack.pop()
        if is_class:
            class_stack.pop()

    # --- Call name resolution --------------------------------------------
    def _resolve_call_name(self, call_node: ast.Call) -> Optional[str]:
        fn = call_node.func
        if isinstance(fn, ast.Name):
            return fn.id
        if isinstance(fn, ast.Attribute):
            parts = []
            cur = fn
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return None

    def _is_interactive(self, name: str) -> bool:
        if name in INTERACTIVE_FUNCS:
            return True
        return any(name.endswith(suffix) for suffix in _INTERACTIVE_SUFFIXES)

    def _is_presentation(self, name: str) -> bool:
        if name in PRESENTATION_FUNCS:
            return True
        if self._is_interactive(name):
            return False
        return any(name.endswith(suffix) for suffix in _PRESENTATION_SUFFIXES)

    # --- Literal extraction ----------------------------------------------
    def _extract_call_literal(self, call_node: ast.Call) -> str:
        """
        Get a short preview of the first string-ish argument to a call.
        Handles plain strings, f-strings, and simple string concatenation.
        """
        for arg in call_node.args:
            text = None

            # plain string: print("hello")
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                text = arg.value

            # f-string: console.print(f"[bold]{name}[/bold]")
            elif isinstance(arg, ast.JoinedStr):
                parts = []
                for v in arg.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        parts.append(v.value)
                    elif isinstance(v, ast.FormattedValue):
                        parts.append("{...}")
                text = "".join(parts)

            # concatenation: print("a" "b") or print("a" + var)
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                left = arg.left
                if isinstance(left, ast.Constant) and isinstance(left.value, str):
                    text = left.value + "..."

            if text:
                text = text.replace("\n", " ").replace("\r", " ").strip()
                # collapse runs of whitespace to keep output readable
                text = re.sub(r"\s+", " ", text)
                if len(text) > 72:
                    text = text[:69] + "..."
                return text

        # also check keyword args (e.g. Console.print("x", style="bold"))
        for kw in call_node.keywords:
            if kw.arg in ("msg", "message", "text"):
                v = kw.value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    text = v.value
                    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
                    return text[:72] + ("..." if len(text) > 72 else "")

        return ""

# ============================================
# NODE FORMATTER
# ============================================
class NodeFormatter:
    """Format AST nodes for clean display"""

    @staticmethod
    def format(node: ast.AST, context: dict = None, source_cache: SourceCache = None,
               lexical: Optional[LexicalReport] = None) -> Optional[str]:
        context = context or {}
        node_type = type(node).__name__
        line_num = getattr(node, 'lineno', 0)
        end_line = getattr(node, 'end_lineno', line_num)

        badges = NodeFormatter._lexical_badges(node, line_num, end_line, lexical)

        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            bases_str = f"({', '.join(bases)})" if bases else ""
            methods = [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]
            public_methods = [m for m in methods if not m.name.startswith('_')]
            private_methods = [m for m in methods if m.name.startswith('_') and m.name != '__init__']

            method_info = ""
            if methods:
                method_info = f" ({len(public_methods)} public, {len(private_methods)} private)"

            line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
            return f"\U0001f3db\ufe0f  class {node.name}{bases_str}{method_info}{badges}{line_info}"

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = "\u26a1 " if isinstance(node, ast.AsyncFunctionDef) else ""
            is_method = any(arg.arg in ['self', 'cls'] for arg in node.args.args)

            args = []
            defaults = node.args.defaults
            for i, arg in enumerate(node.args.args):
                if arg.arg in ['self', 'cls']:
                    continue
                default_idx = i - len(node.args.args) + len(defaults)
                if default_idx >= 0 and default_idx < len(defaults):
                    default_val = ast.unparse(defaults[default_idx])
                    args.append(f"{arg.arg}={default_val}")
                else:
                    args.append(arg.arg)

            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")

            args_str = ", ".join(args)

            if is_method:
                icon = "\U0001f512" if node.name.startswith('_') and node.name != '__init__' else "\U0001f527"
            else:
                icon = "\u25b6\ufe0f"

            decorators = ""
            if node.decorator_list:
                decorator_names = []
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Name):
                        decorator_names.append(deco.id)
                    elif isinstance(deco, ast.Attribute):
                        decorator_names.append(ast.unparse(deco))
                if decorator_names:
                    decorators = f" \U0001f3a8[{', '.join(decorator_names)}]"

            line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
            return f"{icon} {is_async}{node.name}({args_str}){decorators}{badges}{line_info}"

        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"import {', '.join(names)}{badges}{line_info}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = [alias.name for alias in node.names]
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"from {module} import {', '.join(names)}{badges}{line_info}"

        elif isinstance(node, ast.If):
            try:
                cond = ast.unparse(node.test)
                if len(cond) > 30:
                    cond = cond[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\u2753 if {cond}{badges}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\u2753 if{badges}{line_info}"

        elif isinstance(node, ast.For):
            try:
                target = ast.unparse(node.target)
                iter_obj = ast.unparse(node.iter)
                if len(iter_obj) > 30:
                    iter_obj = iter_obj[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 for {target} in {iter_obj}{badges}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 for{badges}{line_info}"

        elif isinstance(node, ast.While):
            try:
                cond = ast.unparse(node.test)
                if len(cond) > 30:
                    cond = cond[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 while {cond}{badges}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 while{badges}{line_info}"

        elif isinstance(node, ast.Try):
            handlers = len(node.handlers)
            has_finally = bool(node.finalbody)
            has_else = bool(node.orelse)
            info = []
            if handlers:
                info.append(f"{handlers} except")
            if has_else:
                info.append("else")
            if has_finally:
                info.append("finally")
            suffix = f" ({', '.join(info)})" if info else ""
            line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
            return f"\U0001f6e1\ufe0f try{suffix}{badges}{line_info}"

        elif isinstance(node, ast.With):
            try:
                items = [ast.unparse(item.context_expr) for item in node.items]
                items_str = ", ".join(items)
                if len(items_str) > 30:
                    items_str = items_str[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f4c2 with {items_str}{badges}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f4c2 with{badges}{line_info}"

        elif isinstance(node, ast.Return):
            if node.value:
                try:
                    val = ast.unparse(node.value)
                    if len(val) > 30:
                        val = val[:27] + "..."
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\u21a9\ufe0f  return {val}{badges}{line_info}"
                except Exception:
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\u21a9\ufe0f  return{badges}{line_info}"
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"\u21a9\ufe0f  return{badges}{line_info}"

        elif isinstance(node, ast.Assign):
            targets = [ast.unparse(t) for t in node.targets]
            try:
                val = ast.unparse(node.value)
                if len(val) > 30:
                    val = val[:27] + "..."
                if isinstance(node.value, ast.Constant) and len(str(node.value.value)) < 20:
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\U0001f4dd {', '.join(targets)} = {node.value.value}{badges}{line_info}"
                line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                return f"\U0001f4dd {', '.join(targets)} = {val}{badges}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                return f"\U0001f4dd {', '.join(targets)} = ...{badges}{line_info}"

        elif isinstance(node, ast.Module):
            return f"\U0001f4c4 Module{badges}"

        else:
            return None

    @staticmethod
    def _lexical_badges(node: ast.AST, line_num: int, end_line: int,
                        lexical: Optional[LexicalReport]) -> str:
        if lexical is None or line_num == 0:
            return ""
        tags = []

        if line_num in lexical.docstrings:
            tags.append(f"{Colors.GREEN}\U0001f4d6{Colors.END}")

        if end_line >= line_num:
            for word, line_nos in lexical.markers.items():
                if any(line_num <= ln <= end_line for ln in line_nos):
                    tags.append(f"{Colors.YELLOW}\u26a0{word}{Colors.END}")
                    break

        if end_line >= line_num and any(line_num <= s <= end_line for s, _, _ in lexical.long_strings):
            tags.append(f"{Colors.CYAN}\U0001f9f5{Colors.END}")

        if any(line_num <= ln <= end_line for ln in lexical.bare_excepts):
            tags.append(f"{Colors.RED}\U0001f41b{Colors.END}")

        if any(line_num <= ln <= end_line for ln, _, _, _ in lexical.interactive_calls):
            tags.append(f"{Colors.YELLOW}\u2328\ufe0f{Colors.END}")

        return (" " + " ".join(tags)) if tags else ""

# ============================================
# FILTERS
# ============================================
class StructureFilter:
    SHOW_ALWAYS = {
        ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef,
        ast.Import, ast.ImportFrom,
    }
    SHOW_INSIDE = {
        ast.If, ast.For, ast.While, ast.Try, ast.With,
        ast.Return, ast.Assign, ast.Await, ast.Raise, ast.Assert,
        ast.Break, ast.Continue, ast.Yield, ast.YieldFrom,
        ast.AnnAssign, ast.AugAssign,
    }
    SKIP = {
        ast.Constant, ast.Name, ast.Expr, ast.Pass,
        ast.Load, ast.Store, ast.Del, ast.arguments, ast.arg,
        ast.keyword, ast.alias, ast.comprehension, ast.withitem,
        ast.ExceptHandler, ast.Attribute, ast.Subscript, ast.Slice,
        ast.BinOp, ast.Compare, ast.BoolOp, ast.UnaryOp,
        ast.List, ast.Tuple, ast.Dict, ast.Set,
        ast.FormattedValue, ast.JoinedStr,
    }

    @staticmethod
    def is_important(node: ast.AST) -> bool:
        node_type = type(node)
        if node_type in StructureFilter.SKIP:
            return False
        if node_type in StructureFilter.SHOW_ALWAYS:
            return True
        return node_type in StructureFilter.SHOW_INSIDE

# ============================================
# TREE BUILDER
# ============================================
class TreeNode:
    def __init__(self, label: str, node: ast.AST = None, line: int = 0,
                 end_line: int = 0, node_type: str = "", source_snippet: str = ""):
        self.label = label
        self.node = node
        self.line = line
        self.end_line = end_line
        self.node_type = node_type
        self.source_snippet = source_snippet
        self.children: List[TreeNode] = []

    def add_child(self, child: 'TreeNode'):
        self.children.append(child)

class TreeBuilder:
    def __init__(self, source_cache: SourceCache = None,
                 lexical: Optional[LexicalReport] = None):
        self.formatter = NodeFormatter()
        self.filter = StructureFilter()
        self.imports = []
        self.source_cache = source_cache
        self.lexical = lexical
        self.stats = {
            'classes': 0,
            'functions': 0,
            'methods': 0,
            'imports': 0,
        }
        self._current_class_name = None

    def build(self, node: ast.AST, depth: int = 0, in_class: bool = False) -> Optional[TreeNode]:
        if depth == 0 and isinstance(node, (ast.Import, ast.ImportFrom)):
            label = self.formatter.format(node, source_cache=self.source_cache, lexical=self.lexical)
            if label:
                self.imports.append(label)
                self.stats['imports'] += 1
            return None

        if isinstance(node, ast.ClassDef):
            self.stats['classes'] += 1
            self._current_class_name = node.name
            in_class = True

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if in_class:
                self.stats['methods'] += 1
            else:
                self.stats['functions'] += 1

        label = self.formatter.format(node, source_cache=self.source_cache, lexical=self.lexical)
        if label is None:
            return self._process_children(node, depth, in_class)

        line_num = getattr(node, 'lineno', 0)
        end_line = getattr(node, 'end_lineno', line_num)
        snippet = ""

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if self.source_cache and line_num > 0:
                snippet = self.source_cache.get_snippet(line_num, end_line, context=0)

        tree_node = TreeNode(label, node, line_num, end_line, type(node).__name__, snippet)

        for child in ast.iter_child_nodes(node):
            child_node = self.build(child, depth + 1, in_class)
            if child_node:
                if isinstance(child_node, list):
                    tree_node.children.extend(child_node)
                else:
                    tree_node.children.append(child_node)

        if tree_node.children:
            tree_node.children = [c for c in tree_node.children if c]

        if isinstance(node, ast.ClassDef):
            self._current_class_name = None

        return tree_node

    def _process_children(self, node: ast.AST, depth: int, in_class: bool) -> List[TreeNode]:
        results = []
        for child in ast.iter_child_nodes(node):
            child_node = self.build(child, depth + 1, in_class)
            if child_node:
                if isinstance(child_node, list):
                    results.extend(child_node)
                else:
                    results.append(child_node)
        return results

# ============================================
# RENDERER
# ============================================
class Renderer:
    def render(self, node: TreeNode, prefix: str = "", is_last: bool = True,
               show_snippets: bool = False) -> List[str]:
        lines = []

        if prefix:
            connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
            lines.append(f"{prefix}{connector}{node.label}")
        else:
            lines.append(node.label)

        if show_snippets and node.source_snippet and isinstance(
                node.node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            indent = prefix + ("    " if is_last else "\u2502   ")
            for line in node.source_snippet.split('\n'):
                lines.append(f"{indent}   {line}")

        children = node.children
        if children:
            child_prefix = prefix + ("    " if is_last else "\u2502   ")
            for i, child in enumerate(children):
                is_last_child = (i == len(children) - 1)
                lines.extend(self.render(child, child_prefix, is_last_child, show_snippets))

        return lines

    def render_imports(self, imports: List[str]) -> List[str]:
        if not imports:
            return []
        out = ["\U0001f4e6 Imports"]
        for i, imp in enumerate(imports):
            connector = "\u2514\u2500\u2500 " if i == len(imports) - 1 else "\u251c\u2500\u2500 "
            out.append(f"   {connector}{imp}")
        return out

# ============================================
# CALL GRAPH BUILDER
# ============================================
_COMMON_BUILTINS = {
    'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict',
    'set', 'tuple', 'isinstance', 'getattr', 'setattr', 'hasattr', 'super',
    'open', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'any',
    'all', 'min', 'max', 'sum', 'abs', 'round', 'type', 'repr', 'format',
    'iter', 'next', 'vars', 'issubclass', 'staticmethod', 'classmethod',
    'property', 'exit', 'input',
}


class CallGraphBuilder(ast.NodeVisitor):
    def __init__(self):
        self.class_stack: List[str] = []
        self.scope_stack: List[str] = []
        self.edges: Set[Tuple[str, str]] = set()
        self.defined: Set[str] = set()
        self.defined_bare: Dict[str, List[str]] = defaultdict(list)

    def _qualify(self, name: str) -> str:
        if self.class_stack:
            return f"{self.class_stack[-1]}.{name}"
        return name

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def _visit_func(self, node):
        qualified = self._qualify(node.name)
        self.defined.add(qualified)
        self.defined_bare[node.name].append(qualified)
        self.scope_stack.append(qualified)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_func(node)

    def visit_Call(self, node: ast.Call):
        if self.scope_stack:
            caller = self.scope_stack[-1]
            callee = self._resolve_callee(node.func)
            if callee:
                self.edges.add((caller, callee))
        self.generic_visit(node)

    def _resolve_callee(self, func_node: ast.AST) -> Optional[str]:
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            if isinstance(func_node.value, ast.Name):
                if func_node.value.id in ('self', 'cls') and self.class_stack:
                    return f"{self.class_stack[-1]}.{func_node.attr}"
                return f"{func_node.value.id}.{func_node.attr}"
            try:
                return ast.unparse(func_node)
            except Exception:
                return func_node.attr
        return None

    def is_internal(self, callee: str) -> bool:
        if callee in self.defined:
            return True
        bare = callee.rsplit('.', 1)[-1]
        return bare in self.defined_bare and len(self.defined_bare[bare]) >= 1 and '.' in callee

    def is_builtin(self, callee: str) -> bool:
        return callee in _COMMON_BUILTINS

# ============================================
# CALL GRAPH RENDERERS
# ============================================
class CallGraphRenderer:
    def __init__(self, graph: CallGraphBuilder, internal_only: bool = False):
        self.graph = graph
        self.internal_only = internal_only

    def _filtered_edges(self) -> List[Tuple[str, str, bool]]:
        out = []
        for caller, callee in sorted(self.graph.edges):
            internal = self.graph.is_internal(callee)
            if self.internal_only and not internal:
                continue
            out.append((caller, callee, internal))
        return out

    def render_text(self) -> List[str]:
        edges = self._filtered_edges()
        if not edges:
            return [f"{Colors.DIM}(no calls found){Colors.END}"]

        by_caller: Dict[str, List[Tuple[str, bool]]] = defaultdict(list)
        for caller, callee, internal in edges:
            by_caller[caller].append((callee, internal))

        lines = [f"{Colors.BOLD}\U0001f578\ufe0f  Call Graph{Colors.END}"]
        for caller in sorted(by_caller):
            lines.append(f"{Colors.CYAN}{caller}{Colors.END}")
            callees = by_caller[caller]
            for i, (callee, internal) in enumerate(callees):
                is_last = (i == len(callees) - 1)
                connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
                if internal:
                    marker = f"{Colors.GREEN}{callee}{Colors.END}"
                elif self.graph.is_builtin(callee):
                    marker = f"{Colors.GRAY}{callee} (builtin){Colors.END}"
                else:
                    marker = f"{Colors.YELLOW}{callee} (external){Colors.END}"
                lines.append(f"   {connector}{marker}")
        return lines

    def render_mermaid(self) -> str:
        edges = self._filtered_edges()
        id_map: Dict[str, str] = {}

        def node_id(name: str) -> str:
            if name not in id_map:
                id_map[name] = f"n{len(id_map)}"
            return id_map[name]

        lines = ["flowchart TD"]
        style_lines = []
        for caller, callee, internal in edges:
            c_id = node_id(caller)
            e_id = node_id(callee)
            lines.append(f'    {c_id}["{caller}"] --> {e_id}["{callee}"]')
            if not internal:
                cls = "builtinNode" if self.graph.is_builtin(callee) else "externalNode"
                style_lines.append(f"    class {e_id} {cls};")

        lines.append("    classDef externalNode fill:#fff3cd,stroke:#c99a2e;")
        lines.append("    classDef builtinNode fill:#eee,stroke:#999,color:#888;")
        lines.extend(style_lines)
        return "\n".join(lines)

    def render_dot(self) -> str:
        edges = self._filtered_edges()
        lines = ["digraph CallGraph {", '    rankdir="LR";',
                 '    node [shape=box, fontname="Helvetica"];']
        seen_nodes: Set[str] = set()

        def escape(name: str) -> str:
            return name.replace('"', '\\"')

        for caller, callee, internal in edges:
            for n in (caller, callee):
                if n not in seen_nodes:
                    seen_nodes.add(n)
                    if n == callee and not internal:
                        color = "gray" if self.graph.is_builtin(n) else "#c99a2e"
                        style = 'style=dashed,' if self.graph.is_builtin(n) else ''
                        lines.append(f'    "{escape(n)}" [{style}color="{color}"];')
            lines.append(f'    "{escape(caller)}" -> "{escape(callee)}";')

        lines.append("}")
        return "\n".join(lines)

# ============================================
# MAIN
# ============================================
def main():
    if len(sys.argv) < 2:
        print(f"{Colors.RED}Error: Please provide a Python file{Colors.END}")
        print(f"Usage: python {sys.argv[0]} <filename.py> [--snippets] [--no-lexical]")
        print(f"       python {sys.argv[0]} <filename.py> --callgraph "
              f"[--graph-format text|mermaid|dot] [--internal-only] [--output FILE]")
        print(f"       python {sys.argv[0]} <filename.py> --stats|--comments|--todos|--interactive|--ui")
        sys.exit(1)

    filename = sys.argv[1]
    show_snippets = '--snippets' in sys.argv or '-s' in sys.argv
    do_callgraph = '--callgraph' in sys.argv or '-g' in sys.argv
    internal_only = '--internal-only' in sys.argv
    no_lexical = '--no-lexical' in sys.argv
    only_stats = '--stats' in sys.argv
    only_comments = '--comments' in sys.argv
    only_todos = '--todos' in sys.argv
    only_interactive = '--interactive' in sys.argv
    only_ui = '--ui' in sys.argv

    graph_format = 'text'
    if '--graph-format' in sys.argv:
        idx = sys.argv.index('--graph-format')
        if idx + 1 < len(sys.argv):
            graph_format = sys.argv[idx + 1]

    output_path = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    if not os.path.exists(filename):
        print(f"{Colors.RED}Error: File '{filename}' not found{Colors.END}")
        sys.exit(1)

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            source_lines = f.readlines()
        source_cache = SourceCache(source_lines)

        # --- Lexical pass runs first (doesn't need AST) -----------------
        lexical: Optional[LexicalReport] = None
        if not no_lexical:
            lexer = LexicalAnalyzer(source_lines, filename=filename)
            try:
                parse_tree = ast.parse(''.join(source_lines), filename=filename)
                lexical = lexer.analyze(parse_tree)
            except SyntaxError:
                lexical = lexer.analyze(None)

        # --- Lexical-only output modes ----------------------------------
        if lexical is not None and (only_stats or only_comments or only_todos
                                    or only_interactive or only_ui):
            print(f"{Colors.BOLD}{Colors.HEADER}\U0001f4c4 {filename}{Colors.END}\n")
            if only_stats:
                for line in lexical.render_summary():
                    print(line)
            if only_comments:
                print()
                for line in lexical.render_comments():
                    print(line)
            if only_todos:
                print()
                for line in lexical.render_markers():
                    print(line)
            if only_interactive:
                print()
                for line in lexical.render_interactive():
                    print(line)
            if only_ui:
                print()
                for line in lexical.render_ui_flow():
                    print(line)
            return

        # --- AST parse --------------------------------------------------
        tree = ast.parse(''.join(source_lines), filename=filename)

        # --- Callgraph mode --------------------------------------------
        if do_callgraph:
            cg = CallGraphBuilder()
            cg.visit(tree)
            renderer = CallGraphRenderer(cg, internal_only=internal_only)

            print(f"{Colors.BOLD}{Colors.HEADER}\U0001f578\ufe0f  Call graph for {filename}{Colors.END}\n")

            output = None
            if graph_format == 'mermaid':
                output = renderer.render_mermaid()
                print(output)
            elif graph_format == 'dot':
                output = renderer.render_dot()
                print(output)
            else:
                for line in renderer.render_text():
                    print(line)

            if output_path and output is not None:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(output)
                print(f"\n{Colors.GREEN}\u2705 Wrote {graph_format} graph to {output_path}{Colors.END}")
                if graph_format == 'dot':
                    print(f"{Colors.DIM}\U0001f4a1 Render with: dot -Tsvg {output_path} -o callgraph.svg{Colors.END}")
                elif graph_format == 'mermaid':
                    print(f"{Colors.DIM}\U0001f4a1 Paste into a .md file in a ```mermaid fence, or use mermaid.live{Colors.END}")
            return

        # --- Normal structure mode --------------------------------------
        builder = TreeBuilder(source_cache, lexical=lexical)
        root = builder.build(tree)

        renderer = Renderer()
        print(f"{Colors.BOLD}{Colors.HEADER}\U0001f4c4 {filename}{Colors.END}\n")

        # Lexical summary goes first
        if lexical is not None:
            for line in lexical.render_summary():
                print(line)
            print()

        # Marker warnings (compact)
        if lexical is not None and lexical.markers:
            for line in lexical.render_markers():
                print(line)
            print()

        # Interactive warnings (compact, with strings)
        if lexical is not None and lexical.interactive_calls:
            for line in lexical.render_interactive():
                print(line)
            print()

        if builder.imports:
            for line in renderer.render_imports(builder.imports):
                print(line)
            print()

        if root and root.children:
            for i, child in enumerate(root.children):
                is_last = (i == len(root.children) - 1)
                for line in renderer.render(child, "", is_last, show_snippets):
                    print(line)
                if not is_last:
                    print()

        print(f"\n{Colors.GREEN}\u2705 Parsed successfully{Colors.END}")
        print(f"\U0001f4ca Total AST nodes: {len(list(ast.walk(tree)))}")
        print(f"\U0001f4e6 Imports: {builder.stats['imports']}")
        print(f"\U0001f3db\ufe0f  Classes: {builder.stats['classes']}")
        print(f"\U0001f527 Methods: {builder.stats['methods']}")
        print(f"\u25b6\ufe0f  Functions: {builder.stats['functions']}")

        if builder.stats['classes'] > 0:
            print(f"\U0001f4c8 Avg methods per class: "
                  f"{builder.stats['methods'] / builder.stats['classes']:.1f}")

        # Docstring coverage uses total defs from the AST walk
        if lexical is not None:
            total_defs = builder.stats['classes'] + builder.stats['functions'] + builder.stats['methods']
            have, pct = lexical.docstring_coverage(total_defs)
            print(f"\U0001f4d6 Docstring coverage: {have}/{total_defs} ({pct:.1f}%)")

        if show_snippets:
            print(f"\n{Colors.DIM}\U0001f4a1 Tip: Use --snippets to show code blocks{Colors.END}")

        print(f"{Colors.DIM}\U0001f4a1 Tip: Use --callgraph to see who calls whom{Colors.END}")
        if lexical is not None:
            print(f"{Colors.DIM}\U0001f4a1 Tip: Use --stats / --comments / --todos / --interactive / --ui for lexical detail{Colors.END}")

    except SyntaxError as e:
        print(f"{Colors.RED}Syntax Error: {e}{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.END}")
        sys.exit(1)

if __name__ == "__main__":
    main()
