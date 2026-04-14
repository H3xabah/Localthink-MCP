"""
Pure AST-based public API surface extractor for Python files.
No LLM, no network — instant, deterministic, works fully offline.
Other languages fall back to the LLM via server.py.
"""
import ast


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _DUNDER_KEEP(name: str) -> bool:
    """Dunders worth showing in a class surface."""
    return name in (
        "__init__", "__new__", "__call__",
        "__enter__", "__exit__",
        "__repr__", "__str__",
        "__len__", "__iter__", "__next__",
        "__getitem__", "__setitem__", "__delitem__",
        "__contains__", "__bool__",
        "__add__", "__sub__", "__mul__", "__truediv__",
        "__eq__", "__lt__", "__le__", "__gt__", "__ge__",
        "__hash__", "__await__", "__aenter__", "__aexit__",
    )


def _fmt_args(args: ast.arguments) -> str:
    """Format an ast.arguments node into a human-readable signature string."""
    parts: list[str] = []

    # positional-only args (Python 3.8+)
    posonlyargs = getattr(args, "posonlyargs", [])
    n_po = len(posonlyargs)
    n_po_defaults = max(0, n_po - (len(args.defaults) - len(args.args)))
    for i, arg in enumerate(posonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        di = i - (n_po - n_po_defaults)
        default = f" = {ast.unparse(args.defaults[di])}" if di >= 0 else ""
        parts.append(f"{arg.arg}{ann}{default}")
    if n_po:
        parts.append("/")

    # regular args
    n_reg = len(args.args)
    n_reg_defaults = len(args.defaults)
    for i, arg in enumerate(args.args):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        di = i - (n_reg - n_reg_defaults)
        default = f" = {ast.unparse(args.defaults[di])}" if di >= 0 else ""
        parts.append(f"{arg.arg}{ann}{default}")

    # *args
    if args.vararg:
        ann = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
        parts.append(f"*{args.vararg.arg}{ann}")
    elif args.kwonlyargs:
        parts.append("*")

    # keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        ann = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        kd = args.kw_defaults[i]
        default = f" = {ast.unparse(kd)}" if kd is not None else ""
        parts.append(f"{arg.arg}{ann}{default}")

    # **kwargs
    if args.kwarg:
        ann = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        parts.append(f"**{args.kwarg.arg}{ann}")

    return ", ".join(parts)


def _fmt_func(node: ast.FunctionDef | ast.AsyncFunctionDef, indent: str = "") -> list[str]:
    lines: list[str] = []
    for d in node.decorator_list:
        lines.append(f"{indent}@{ast.unparse(d)}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    kw = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    lines.append(f"{indent}{kw} {node.name}({_fmt_args(node.args)}){ret}: ...")
    return lines


def extract_python_surface(source: str) -> str:
    """
    Extract public API surface from Python source using the stdlib AST.
    Returns a skeleton of signatures, class definitions, and top-level constants.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"[SyntaxError — cannot parse: {e}]"

    output: list[str] = []

    for node in ast.iter_child_nodes(tree):  # top-level only
        # ── Functions ─────────────────────────────────────────────────────
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name):
                continue
            output.extend(_fmt_func(node))
            output.append("")

        # ── Classes ───────────────────────────────────────────────────────
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name):
                continue
            bases = [ast.unparse(b) for b in node.bases]
            kws = [f"{k.arg}={ast.unparse(k.value)}" for k in node.keywords if k.arg]
            all_bases = bases + kws
            base_str = f"({', '.join(all_bases)})" if all_bases else ""
            for d in node.decorator_list:
                output.append(f"@{ast.unparse(d)}")
            output.append(f"class {node.name}{base_str}:")

            method_lines: list[str] = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _is_public(item.name) or _DUNDER_KEEP(item.name):
                        method_lines.extend(_fmt_func(item, indent="    "))
                        method_lines.append("")

            if method_lines:
                output.extend(method_lines)
            else:
                output.append("    ...")
            output.append("")

        # ── Top-level CONSTANT assignments ────────────────────────────────
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and _is_public(target.id):
                    try:
                        output.append(f"{target.id} = {ast.unparse(node.value)}")
                    except Exception:
                        pass

        # ── Annotated assignments (typed module-level vars) ───────────────
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and _is_public(node.target.id):
                ann = ast.unparse(node.annotation)
                val = f" = {ast.unparse(node.value)}" if node.value else ""
                output.append(f"{node.target.id}: {ann}{val}")

    result = "\n".join(output).strip()
    return result if result else "[No public API surface found]"
