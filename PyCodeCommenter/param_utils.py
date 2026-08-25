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
from typing import List, NamedTuple, Optional, Union

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


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
