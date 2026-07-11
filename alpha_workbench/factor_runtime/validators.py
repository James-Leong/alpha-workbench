"""Static checks applied before factor plugin code is imported."""

from __future__ import annotations

import ast
from pathlib import Path


class PluginValidationError(ValueError):
    """Raised when plugin source violates the runtime's static policy."""


_ALLOWED_IMPORTS = {"numpy", "pandas", "typing"}
_ALLOWED_FROM_IMPORTS = {
    "__future__": {"annotations"},
    "alpha_workbench.factor_runtime": {"FactorContext"},
    "typing": {"Any", "Mapping", "Protocol", "Sequence"},
}
_FORBIDDEN_MODULES = {
    "os",
    "pathlib",
    "requests",
    "socket",
    "subprocess",
    "sys",
    "uqer",
}
_FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_FORBIDDEN_ATTRIBUTES = {
    "ctypeslib",
    "fromfile",
    "io",
    "load",
    "memmap",
    "popen",
    "read_csv",
    "read_excel",
    "read_html",
    "read_json",
    "read_parquet",
    "read_pickle",
    "read_sql",
    "read_xml",
    "save",
    "system",
    "to_csv",
    "to_excel",
    "to_json",
    "to_parquet",
    "to_pickle",
    "tofile",
}


def _module_root(module: str) -> str:
    return module.split(".", maxsplit=1)[0]


class _PluginAstValidator(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename

    def fail(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", "?")
        raise PluginValidationError(f"{self.filename}:{line}: {message}")

    def check_import(self, node: ast.AST, module: str) -> None:
        root = _module_root(module)
        if root in _FORBIDDEN_MODULES:
            self.fail(node, f"import of '{root}' is forbidden")
        if module not in _ALLOWED_IMPORTS:
            self.fail(node, f"import of '{module}' is not allowed")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.check_import(node, alias.name)
            if alias.asname in _FORBIDDEN_MODULES | _FORBIDDEN_CALLS:
                self.fail(node, f"import alias {alias.asname!r} is forbidden")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.fail(node, "relative imports are not allowed")
        module = node.module or ""
        allowed_names = _ALLOWED_FROM_IMPORTS.get(module)
        if allowed_names is None:
            self.fail(node, f"from import of '{module}' is not allowed")
        for alias in node.names:
            if alias.name not in allowed_names:
                self.fail(node, f"import of '{module}.{alias.name}' is not allowed")
            if alias.asname in _FORBIDDEN_MODULES | _FORBIDDEN_CALLS:
                self.fail(node, f"import alias {alias.asname!r} is forbidden")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callable_name: str | None = None
        if isinstance(node.func, ast.Name):
            callable_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callable_name = node.func.attr
        if callable_name in _FORBIDDEN_CALLS | _FORBIDDEN_ATTRIBUTES:
            self.fail(node, f"call to '{callable_name}' is forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.fail(node, f"dunder attribute '{node.attr}' is forbidden")
        if node.attr in _FORBIDDEN_ATTRIBUTES:
            self.fail(node, f"attribute '{node.attr}' is forbidden")
        self.generic_visit(node)


def validate_plugin_source(source: str, *, filename: str = "<factor.py>") -> None:
    """Parse source and reject imports, calls, and attributes outside policy."""

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise PluginValidationError(f"invalid Python syntax in {filename}: {exc}") from exc
    _validate_module_structure(tree, filename)
    _PluginAstValidator(filename).visit(tree)


def _validate_module_structure(tree: ast.Module, filename: str) -> None:
    validator = _PluginAstValidator(filename)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is not None and not _is_safe_literal(value):
                validator.fail(node, "module-level assignments must use literal values")
            continue
        if isinstance(node, ast.FunctionDef):
            _validate_function_definition(node, validator)
            continue
        if isinstance(node, ast.ClassDef):
            _validate_class_definition(node, validator)
            continue
        validator.fail(node, f"module-level {type(node).__name__} is not allowed")


def _validate_function_definition(
    node: ast.FunctionDef,
    validator: _PluginAstValidator,
) -> None:
    if node.decorator_list:
        validator.fail(node, "function decorators are not allowed")
    defaults = [*node.args.defaults, *(item for item in node.args.kw_defaults if item)]
    if any(not _is_safe_literal(default) for default in defaults):
        validator.fail(node, "function defaults must use literal values")
    signature_nodes = [
        *(argument.annotation for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs] if argument.annotation),
        *(item for item in [node.args.vararg, node.args.kwarg] if item and item.annotation),
        *([node.returns] if node.returns else []),
    ]
    if any(isinstance(item, ast.Call) for signature in signature_nodes for item in ast.walk(signature)):
        validator.fail(node, "calls in function annotations are not allowed")


def _validate_class_definition(node: ast.ClassDef, validator: _PluginAstValidator) -> None:
    if node.decorator_list or node.keywords:
        validator.fail(node, "class decorators and keywords are not allowed")
    if any(not isinstance(base, (ast.Name, ast.Attribute)) for base in node.bases):
        validator.fail(node, "class bases must be simple names")
    for child in node.body:
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant):
            continue
        if isinstance(child, ast.FunctionDef):
            _validate_function_definition(child, validator)
            continue
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            value = child.value
            if value is not None and not _is_safe_literal(value):
                validator.fail(child, "class assignments must use literal values")
            continue
        validator.fail(child, f"class-level {type(child).__name__} is not allowed")


def _is_safe_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_safe_literal(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is None or _is_safe_literal(key) for key in node.keys
        ) and all(_is_safe_literal(value) for value in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_safe_literal(node.operand)
    return False


def validate_plugin_file(path: str | Path) -> None:
    plugin_path = Path(path)
    validate_plugin_source(
        plugin_path.read_text(encoding="utf-8"),
        filename=str(plugin_path),
    )


validate_plugin_ast = validate_plugin_source
