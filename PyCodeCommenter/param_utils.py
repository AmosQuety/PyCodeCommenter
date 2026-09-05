"""Shared parameter-extraction primitive for PyCodeCommenter.

``func_node.args.args`` only covers regular positional-or-keyword
parameters. It is blind to positional-only parameters (PEP 570),
keyword-only parameters (PEP 3102), and ``*args``/``**kwargs``. Both
``commenter.py`` (docstring generation) and ``validator.py`` (signature/type
checks) independently rebuilt "this function's parameters" from
``func_node.args.args`` alone, so all of them silently ignored the same
categories of parameter. This module is the single shared primitive both
now use instead.
"""

import ast
from typing import Iterator, List, NamedTuple, Optional, Union

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _walk_until(node: ast.AST, boundary_types: tuple) -> Iterator[ast.AST]:
    """Shared traversal for the two scope-bounded walkers below: yields every
    descendant of *node*, without descending past a node whose type is in
    *boundary_types*. The boundary node itself is still yielded, just not
    expanded further.

    Args:
        node (ast.AST): The node whose descendants should be walked.
        boundary_types (tuple): AST node types to yield but not expand into.

    Yields:
        ast.AST: Every descendant node up to each boundary.
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if isinstance(child, boundary_types):
            continue
        stack.extend(ast.iter_child_nodes(child))


def walk_own_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Yields every descendant of *node* without crossing into a nested
    function/class scope.

    ``ast.walk(node)`` descends into nested ``FunctionDef``/
    ``AsyncFunctionDef``/``ClassDef`` bodies too, so e.g. a ``return``/
    ``yield``/``raise`` inside a nested ``def`` gets misattributed to
    *node*'s own scope. This stops at those boundaries instead. *node*
    itself is not yielded, matching ``ast.walk``'s behavior of yielding
    only descendants.

    Use this for anything that must belong to *exactly* this function --
    a ``return``/``yield``/``raise`` inside a nested ``def`` is the nested
    function's, never the outer one's. For a ``self.x = ...`` scan, where a
    nested *closure* (not a nested class) legitimately shares the same
    ``self``, use :func:`walk_skipping_nested_classes` instead.

    Args:
        node (ast.AST): The node whose own scope should be walked (typically
            a function or async function node's body).

    Returns:
        Iterator[ast.AST]: Every descendant node in *node*'s own scope.
    """
    return _walk_until(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def walk_skipping_nested_classes(node: ast.AST) -> Iterator[ast.AST]:
    """Yields every descendant of *node* without crossing into a nested
    class's body -- but *does* descend into nested functions/closures.

    A nested ``def`` inside e.g. ``__init__`` still closes over the same
    ``self``, so ``self.x = ...`` inside it is a real attribute of the
    instance being constructed and must still be found. A nested ``class``
    inside ``__init__`` has its own, different ``self`` in its own methods,
    so ``self.x = ...`` there belongs to *that* class, not *node*'s.

    Args:
        node (ast.AST): The node whose scope should be walked (typically a
            function or async function node's body).

    Returns:
        Iterator[ast.AST]: Every descendant node, excluding nested classes'
            internals.
    """
    return _walk_until(node, (ast.ClassDef,))


class Parameter(NamedTuple):
    """One parameter of a function, normalized across every kind
    ``ast.arguments`` can hold."""

    arg: ast.arg
    kind: str  # "positional", "vararg", "kwonly", or "kwarg"
    default: Optional[ast.expr]

    @property
    def name(self) -> str:
        return self.arg.arg

    @property
    def display_name(self) -> str:
        """Name as it should appear in (and be matched against) a docstring
        Args section."""
        if self.kind == "vararg":
            return f"*{self.arg.arg}"
        if self.kind == "kwarg":
            return f"**{self.arg.arg}"
        return self.arg.arg


def get_all_parameters(func_node: FunctionNode) -> List[Parameter]:
    """Returns every parameter of *func_node* in declaration order.

    Covers positional-only, regular positional-or-keyword, ``*args``,
    keyword-only, and ``**kwargs`` parameters -- the full grammar
    ``ast.arguments`` can express, not just ``func_node.args.args``.

    Args:
        func_node (FunctionNode): The function (or async function) node.

    Returns:
        List[Parameter]: Every parameter, each paired with its kind and
            default value node (``None`` if it has no default).
    """
    params: List[Parameter] = []

    positional = [*func_node.args.posonlyargs, *func_node.args.args]
    defaults = func_node.args.defaults
    padded_defaults = [None] * (len(positional) - len(defaults)) + list(defaults)
    for arg, default in zip(positional, padded_defaults):
        params.append(Parameter(arg, "positional", default))

    if func_node.args.vararg:
        params.append(Parameter(func_node.args.vararg, "vararg", None))

    for arg, default in zip(func_node.args.kwonlyargs, func_node.args.kw_defaults):
        params.append(Parameter(arg, "kwonly", default))

    if func_node.args.kwarg:
        params.append(Parameter(func_node.args.kwarg, "kwarg", None))

    return params


def exclude_self_cls(params: List[Parameter]) -> List[Parameter]:
    """Strips a leading ``self``/``cls`` parameter, if present.

    Matches the existing self/cls heuristic used across the codebase: only
    the first parameter is ever considered, and only when it's positional.

    Args:
        params (List[Parameter]): Parameters as returned by
            ``get_all_parameters``.

    Returns:
        List[Parameter]: *params* with a leading self/cls dropped, unchanged
            otherwise.
    """
    if (
        params
        and params[0].kind == "positional"
        and params[0].arg.arg in ("self", "cls")
    ):
        return params[1:]
    return params
