"""Plain-English statements read directly off a function's code.

Everything here states something the source itself says -- the condition
guarding a ``raise``, the expression a boolean function returns -- and
returns ``None`` whenever the statement would not be exact. ``None`` means
"leave the guess marker in place"; it is never a reason to fall back to a
looser phrasing. See ``inference.GUESS_MARKER`` for why a marked gap is
preferred over plausible-sounding text.
"""

import ast
from typing import Dict, List, Optional

try:
    from .param_utils import FunctionNode, walk_own_scope
except (ImportError, ValueError):
    from param_utils import FunctionNode, walk_own_scope

# Longer conditions stop reading as a sentence and start reading as code
# pasted into prose; those keep the marker for a human to summarise.
MAX_CONDITION_LENGTH = 60


def raise_sites(func_node: FunctionNode) -> Dict[str, List[ast.Raise]]:
    """Groups the function's own ``raise`` statements by exception class.

    Only ``raise SomeError(...)`` names its class at the raise site. A bare
    re-raise and ``raise err`` (an already-constructed instance) are skipped:
    reading their class would need data-flow analysis.

    Args:
        func_node (FunctionNode): The function to inspect.

    Returns:
        Dict[str, List[ast.Raise]]: Raise statements by short class name
            (``errors.ConfigError`` -> ``ConfigError``), in source order.
    """
    raises = [
        node
        for node in walk_own_scope(func_node)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
    ]
    sites: Dict[str, List[ast.Raise]] = {}
    for node in sorted(raises, key=lambda n: (n.lineno, n.col_offset)):
        name = _short_name(node.exc.func)
        if name is not None:
            sites.setdefault(name, []).append(node)
    return sites


def describe_raise_condition(
    func_node: FunctionNode, raise_nodes: List[ast.Raise]
) -> Optional[str]:
    """States when an exception is raised, if every raise site says so exactly.

    A site's condition is exact only when its check sits directly in the
    function body: an ``if`` (not an ``elif``), an ``except`` clause, or an
    unconditional ``raise`` in a function with no ``return``. Anything
    nested deeper depends on outer conditions or loop variables that one
    clause can't capture.

    Args:
        func_node (FunctionNode): The function the raise statements belong to.
        raise_nodes (List[ast.Raise]): Every site raising one exception class.

    Returns:
        Optional[str]: A sentence such as ``"If `x < 0`."``, or ``None`` if
            any site's condition isn't exact -- stating only the known ones
            would read as the complete list.
    """
    parents = _parent_map(func_node)
    conditions = [_site_condition(func_node, node, parents) for node in raise_nodes]
    if not conditions or None in conditions:
        return None
    unique = list(dict.fromkeys(conditions))
    if len(unique) > 1 and "Always" in unique:
        return None
    first, *rest = unique
    return ", or ".join([first] + [c[0].lower() + c[1:] for c in rest]) + "."


def describe_bool_return(func_node: FunctionNode) -> Optional[str]:
    """States what a boolean function's single return expression tests.

    The caller is responsible for having established that the function
    returns ``bool``; this only phrases the one expression it returns.

    Args:
        func_node (FunctionNode): A function whose return type is ``bool``.

    Returns:
        Optional[str]: ``"True if `expr`, otherwise False."``, or ``None``
            when there is more than one return path (no single expression
            describes the result) or the expression is a bare literal.
    """
    returns = [
        node
        for node in walk_own_scope(func_node)
        if isinstance(node, ast.Return) and node.value is not None
    ]
    if len(returns) != 1 or isinstance(returns[0].value, ast.Constant):
        return None
    expression = _short_source(returns[0].value)
    if expression is None:
        return None
    return f"True if `{expression}`, otherwise False."


def _site_condition(
    func_node: FunctionNode, raise_node: ast.Raise, parents: Dict[ast.AST, ast.AST]
) -> Optional[str]:
    """The exact condition for one raise site, without a trailing period."""
    parent = parents.get(raise_node)

    if parent is func_node:
        # An earlier `return` means reaching this line is itself conditional.
        has_return = any(isinstance(n, ast.Return) for n in walk_own_scope(func_node))
        return None if has_return else "Always"

    # Membership of func_node.body excludes `elif`, whose If node lives in
    # the previous branch's orelse and inherits its negated condition.
    if isinstance(parent, ast.If) and parent in func_node.body:
        test = _short_source(parent.test)
        if test is None:
            return None
        return f"If `{test}`" if raise_node in parent.body else f"If `{test}` is false"

    if isinstance(parent, ast.ExceptHandler) and parents.get(parent) in func_node.body:
        caught = _caught_names(parent.type)
        if caught is None:
            return None
        return "If " + " or ".join(f"`{name}`" for name in caught) + " occurs"

    return None


def _caught_names(type_node: Optional[ast.expr]) -> Optional[List[str]]:
    """Exception names an ``except`` clause catches, or ``None`` for a bare
    ``except:`` or a computed expression."""
    if type_node is None:
        return None
    nodes = type_node.elts if isinstance(type_node, ast.Tuple) else [type_node]
    names = [_short_name(node) for node in nodes]
    return None if None in names else names


def _short_name(node: ast.expr) -> Optional[str]:
    """``ValueError`` -> ``ValueError``, ``errors.ConfigError`` ->
    ``ConfigError``; anything else -> ``None``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _short_source(node: ast.expr) -> Optional[str]:
    """The expression's source, if it fits in one readable inline span.

    Colons and backticks are refused: a colon would be misread as a
    "type: description" separator when the docstring is parsed back on the
    next run, and a backtick would end the inline code span early.
    """
    text = ast.unparse(node)
    if len(text) > MAX_CONDITION_LENGTH or any(c in text for c in ":`\n"):
        return None
    return text


def _parent_map(func_node: FunctionNode) -> Dict[ast.AST, ast.AST]:
    """Maps each node in the function's own scope to its parent node."""
    parents: Dict[ast.AST, ast.AST] = {}
    for node in [func_node, *walk_own_scope(func_node)]:
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents
