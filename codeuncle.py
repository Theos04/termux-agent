#!/usr/bin/env python3
"""
ast_viewer.py - Clean Python code structure visualizer with line numbers
Usage: python ast_viewer.py <filename.py> [--snippets]
       python ast_viewer.py <filename.py> --callgraph [--graph-format text|mermaid|dot] [--internal-only] [--output FILE]
"""

import ast
import sys
import os
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict

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

# ============================================
# SOURCE CODE CACHE
# ============================================
class SourceCache:
    """Cache source code lines for reference"""
    def __init__(self, source_lines: List[str]):
        self.lines = source_lines

    def get_snippet(self, start_line: int, end_line: int = None, context: int = 0) -> str:
        """Get a snippet of source code"""
        if end_line is None:
            end_line = start_line

        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.lines), end_line)

        # Add context
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
# NODE FORMATTER
# ============================================
class NodeFormatter:
    """Format AST nodes for clean display"""

    @staticmethod
    def format(node: ast.AST, context: dict = None, source_cache: SourceCache = None) -> Optional[str]:
        """Get a clean label for a node with line numbers"""
        context = context or {}
        node_type = type(node).__name__
        line_num = getattr(node, 'lineno', 0)
        end_line = getattr(node, 'end_lineno', line_num)

        # Classes
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
            return f"\U0001f3db\ufe0f  class {node.name}{bases_str}{method_info}{line_info}"

        # Functions/Methods
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
                if node.name == '__init__':
                    icon = "\U0001f527"
                elif node.name.startswith('_'):
                    icon = "\U0001f512"
                else:
                    icon = "\U0001f527"
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
            return f"{icon} {is_async}{node.name}({args_str}){decorators}{line_info}"

        # Imports
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"import {', '.join(names)}{line_info}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            names = [alias.name for alias in node.names]
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"from {module} import {', '.join(names)}{line_info}"

        # Control flow
        elif isinstance(node, ast.If):
            try:
                cond = ast.unparse(node.test)
                if len(cond) > 30:
                    cond = cond[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\u2753 if {cond}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\u2753 if{line_info}"

        elif isinstance(node, ast.For):
            try:
                target = ast.unparse(node.target)
                iter_obj = ast.unparse(node.iter)
                if len(iter_obj) > 30:
                    iter_obj = iter_obj[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 for {target} in {iter_obj}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 for{line_info}"

        elif isinstance(node, ast.While):
            try:
                cond = ast.unparse(node.test)
                if len(cond) > 30:
                    cond = cond[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 while {cond}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f504 while{line_info}"

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
            return f"\U0001f6e1\ufe0f try{suffix}{line_info}"

        elif isinstance(node, ast.With):
            try:
                items = [ast.unparse(item.context_expr) for item in node.items]
                items_str = ", ".join(items)
                if len(items_str) > 30:
                    items_str = items_str[:27] + "..."
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f4c2 with {items_str}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[lines {line_num}-{end_line}]{Colors.END}" if line_num else ""
                return f"\U0001f4c2 with{line_info}"

        # Return
        elif isinstance(node, ast.Return):
            if node.value:
                try:
                    val = ast.unparse(node.value)
                    if len(val) > 30:
                        val = val[:27] + "..."
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\u21a9\ufe0f  return {val}{line_info}"
                except Exception:
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\u21a9\ufe0f  return{line_info}"
            line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
            return f"\u21a9\ufe0f  return{line_info}"

        # Assignment
        elif isinstance(node, ast.Assign):
            targets = [ast.unparse(t) for t in node.targets]
            try:
                val = ast.unparse(node.value)
                if len(val) > 30:
                    val = val[:27] + "..."
                if isinstance(node.value, ast.Constant) and len(str(node.value.value)) < 20:
                    line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                    return f"\U0001f4dd {', '.join(targets)} = {node.value.value}{line_info}"
                line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                return f"\U0001f4dd {', '.join(targets)} = {val}{line_info}"
            except Exception:
                line_info = f" {Colors.DIM}[line {line_num}]{Colors.END}" if line_num else ""
                return f"\U0001f4dd {', '.join(targets)} = ...{line_info}"

        # Module
        elif isinstance(node, ast.Module):
            return "\U0001f4c4 Module"

        # Skip noise
        else:
            return None

# ============================================
# FILTERS
# ============================================
class StructureFilter:
    """Filter what nodes to show"""

    SHOW_ALWAYS = {
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Import,
        ast.ImportFrom,
    }

    SHOW_INSIDE = {
        ast.If,
        ast.For,
        ast.While,
        ast.Try,
        ast.With,
        ast.Return,
        ast.Assign,
        ast.Await,
        ast.Raise,
        ast.Assert,
        ast.Break,
        ast.Continue,
        ast.Yield,
        ast.YieldFrom,
        ast.AnnAssign,
        ast.AugAssign,
    }

    SKIP = {
        ast.Constant,
        ast.Name,
        ast.Expr,
        ast.Pass,
        ast.Load,
        ast.Store,
        ast.Del,
        ast.arguments,
        ast.arg,
        ast.keyword,
        ast.alias,
        ast.comprehension,
        ast.withitem,
        ast.ExceptHandler,
        ast.Attribute,
        ast.Subscript,
        ast.Slice,
        ast.BinOp,
        ast.Compare,
        ast.BoolOp,
        ast.UnaryOp,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Set,
        ast.FormattedValue,
        ast.JoinedStr,
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
    def __init__(self, source_cache: SourceCache = None):
        self.formatter = NodeFormatter()
        self.filter = StructureFilter()
        self.imports = []
        self.source_cache = source_cache
        self.stats = {
            'classes': 0,
            'functions': 0,
            'methods': 0,
            'imports': 0,
        }
        self._current_class_name = None

    def build(self, node: ast.AST, depth: int = 0, in_class: bool = False) -> Optional[TreeNode]:
        # Collect imports at top level
        if depth == 0 and isinstance(node, (ast.Import, ast.ImportFrom)):
            label = self.formatter.format(node, source_cache=self.source_cache)
            if label:
                self.imports.append(label)
                self.stats['imports'] += 1
            return None

        # Track class
        if isinstance(node, ast.ClassDef):
            self.stats['classes'] += 1
            self._current_class_name = node.name
            in_class = True

        # Track functions/methods
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if in_class:
                self.stats['methods'] += 1
            else:
                self.stats['functions'] += 1

        # Get label with line numbers
        label = self.formatter.format(node, source_cache=self.source_cache)
        if label is None:
            return self._process_children(node, depth, in_class)

        # Get source snippet for important nodes
        line_num = getattr(node, 'lineno', 0)
        end_line = getattr(node, 'end_lineno', line_num)
        snippet = ""

        # Get snippet for classes and functions/methods
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if self.source_cache and line_num > 0:
                snippet = self.source_cache.get_snippet(line_num, end_line, context=0)

        tree_node = TreeNode(
            label, node, line_num, end_line,
            type(node).__name__, snippet
        )

        # Process children
        for child in ast.iter_child_nodes(node):
            child_node = self.build(child, depth + 1, in_class)
            if child_node:
                if isinstance(child_node, list):
                    tree_node.children.extend(child_node)
                else:
                    tree_node.children.append(child_node)

        if tree_node.children:
            tree_node.children = [c for c in tree_node.children if c]

        # Reset class name when leaving class
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

        # Show source snippet if requested and available
        if show_snippets and node.source_snippet and (isinstance(node.node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))):
            indent = prefix + ("    " if is_last else "\u2502   ")
            snippet_lines = node.source_snippet.split('\n')
            for line in snippet_lines:
                lines.append(f"{indent}   {line}")

        children = node.children
        if children:
            child_prefix = prefix + ("    " if is_last else "\u2502   ")
            for i, child in enumerate(children):
                is_last_child = (i == len(children) - 1)
                child_lines = self.render(child, child_prefix, is_last_child, show_snippets)
                lines.extend(child_lines)

        return lines

    def render_imports(self, imports: List[str]) -> List[str]:
        if not imports:
            return []

        import_lines = ["\U0001f4e6 Imports"]
        for i, imp in enumerate(imports):
            is_last = (i == len(imports) - 1)
            connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
            import_lines.append(f"   {connector}{imp}")

        return import_lines

# ============================================
# CALL GRAPH BUILDER
# ============================================
# Names that are almost always builtins / stdlib, used only to group "noise"
# nodes together in text/rendered output rather than as a strict allowlist.
_COMMON_BUILTINS = {
    'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict',
    'set', 'tuple', 'isinstance', 'getattr', 'setattr', 'hasattr', 'super',
    'open', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'any',
    'all', 'min', 'max', 'sum', 'abs', 'round', 'type', 'repr', 'format',
    'iter', 'next', 'vars', 'issubclass', 'staticmethod', 'classmethod',
    'property', 'exit', 'input',
}


class CallGraphBuilder(ast.NodeVisitor):
    """
    Walk a module and build caller -> callee edges.

    Scopes are tracked as qualified names: top-level functions are just
    their name ('main'), methods are 'ClassName.method_name'. Calls made
    via self.foo()/cls.foo() are resolved to the enclosing class's method.
    Everything else is best-effort: a dotted call like `os.path.join(...)`
    is recorded as the literal 'os.path.join' string, and classified as
    "external" unless that exact name happens to match something defined
    in this file.
    """

    def __init__(self):
        self.class_stack: List[str] = []
        self.scope_stack: List[str] = []
        self.edges: Set[Tuple[str, str]] = set()
        self.defined: Set[str] = set()          # qualified names defined in this file
        self.defined_bare: Dict[str, List[str]] = defaultdict(list)  # bare name -> qualified name(s)

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
        """True if callee resolves to something defined in this file."""
        if callee in self.defined:
            return True
        # e.g. "instance.method" where "method" is a known method name
        # and there's exactly one class defining it - best-effort match.
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
        """Returns (caller, callee, is_internal) tuples, filtered per settings."""
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
        lines = ["digraph CallGraph {", '    rankdir="LR";', '    node [shape=box, fontname="Helvetica"];']
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
        print(f"Usage: python {sys.argv[0]} <filename.py> [--snippets]")
        print(f"       python {sys.argv[0]} <filename.py> --callgraph [--graph-format text|mermaid|dot] [--internal-only] [--output FILE]")
        sys.exit(1)

    filename = sys.argv[1]
    show_snippets = '--snippets' in sys.argv or '-s' in sys.argv
    do_callgraph = '--callgraph' in sys.argv or '-g' in sys.argv
    internal_only = '--internal-only' in sys.argv

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

        tree = ast.parse(''.join(source_lines), filename=filename)

        if do_callgraph:
            cg = CallGraphBuilder()
            cg.visit(tree)
            renderer = CallGraphRenderer(cg, internal_only=internal_only)

            print(f"{Colors.BOLD}{Colors.HEADER}\U0001f578\ufe0f  Call graph for {filename}{Colors.END}\n")

            if graph_format == 'mermaid':
                output = renderer.render_mermaid()
                print(output)
            elif graph_format == 'dot':
                output = renderer.render_dot()
                print(output)
            else:
                for line in renderer.render_text():
                    print(line)
                output = None

            if output_path and output is not None:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(output)
                print(f"\n{Colors.GREEN}\u2705 Wrote {graph_format} graph to {output_path}{Colors.END}")
                if graph_format == 'dot':
                    print(f"{Colors.DIM}\U0001f4a1 Render with: dot -Tsvg {output_path} -o callgraph.svg{Colors.END}")
                elif graph_format == 'mermaid':
                    print(f"{Colors.DIM}\U0001f4a1 Paste into a .md file in a ```mermaid fence, or use mermaid.live{Colors.END}")
            return

        builder = TreeBuilder(source_cache)
        root = builder.build(tree)

        renderer = Renderer()
        print(f"{Colors.BOLD}{Colors.HEADER}\U0001f4c4 {filename}{Colors.END}\n")

        if builder.imports:
            import_lines = renderer.render_imports(builder.imports)
            for line in import_lines:
                print(line)
            print()

        if root and root.children:
            for i, child in enumerate(root.children):
                is_last = (i == len(root.children) - 1)
                lines = renderer.render(child, "", is_last, show_snippets)
                for line in lines:
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
            print(f"\U0001f4c8 Avg methods per class: {builder.stats['methods'] / builder.stats['classes']:.1f}")

        if show_snippets:
            print(f"\n{Colors.DIM}\U0001f4a1 Tip: Use --snippets to show code blocks{Colors.END}")

        print(f"{Colors.DIM}\U0001f4a1 Tip: Use --callgraph to see who calls whom{Colors.END}")

    except SyntaxError as e:
        print(f"{Colors.RED}Syntax Error: {e}{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.END}")
        sys.exit(1)

if __name__ == "__main__":
    main()
