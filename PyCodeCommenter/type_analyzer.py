"""
Type inference module for PyCodeCommenter.

This module provides sophisticated type inference for Python code by analyzing
AST nodes. It supports modern Python features including PEP 604 union types (|),
PEP 585 generics (list[int]), and complex type annotations.

Classes:
    TypeAnalyzer: Analyzes Python AST nodes to infer types for variables,
                  arguments, and return values
"""

import ast
import logging
from typing import Any, Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Built-ins whose result is always a bool, whatever the arguments.
_BOOL_BUILTINS = frozenset(
    {"isinstance", "issubclass", "callable", "hasattr", "all", "any"}
)

# str methods that return a str, recognised only when called directly on a
# string literal (`" ".join(...)`), where the receiver's type is certain.
_STR_RETURNING_STR_METHODS = frozenset(
    {
        "join",
        "format",
        "upper",
        "lower",
        "strip",
        "lstrip",
        "rstrip",
        "replace",
        "title",
        "capitalize",
    }
)


class TypeAnalyzer:
    """
    Analyzes Python AST nodes to infer types for variables, arguments, and
    return values. Supports modern Python features like PEP 604 (|) and
    PEP 585 (generics).
    """

    def __init__(self, local_types: Optional[Dict[str, str]] = None):
        """
        Initializes the analyzer with optional pre-known local types.

        Args:
            local_types (Optional[Dict[str, str]]): Dictionary mapping
                variable names to their inferred types.
        """
        self.local_types = local_types or {}

    def infer_type(self, node: Any) -> str:
        """
        Infers the type of an AST node (Argument, Name, Constant, etc.).

        Args:
            node (Any): The AST node to analyze.

        Returns:
            str: The inferred type as a string (e.g., 'int', 'List[str]', 'any').
        """
        try:
            # Handle Argument nodes (with annotations)
            if isinstance(node, ast.arg):
                if node.annotation:
                    return self.get_annotation_type(node.annotation)
                return self.local_types.get(node.arg, "any")

            # Handle Value nodes (Expressions)
            return self.infer_expr_type(node)
        except Exception as e:
            logger.error(f"Error in infer_type: {e}")
            return "any"

    def infer_expr_type(self, expr: Any) -> str:
        """
        Infers type from an expression node.

        Args:
            expr (Any): The expression node to analyze.

        Returns:
            str: The inferred type.
        """
        if isinstance(expr, ast.Constant):
            return type(expr.value).__name__

        if isinstance(expr, (ast.List, ast.ListComp)):
            return "list"

        if isinstance(expr, (ast.Dict, ast.DictComp)):
            return "dict"

        if isinstance(expr, (ast.Set, ast.SetComp)):
            return "set"

        if isinstance(expr, (ast.Tuple)):
            return "tuple"

        if isinstance(expr, ast.Name):
            if expr.id in {"True", "False"}:
                return "bool"
            if expr.id == "None":
                return "NoneType"
            return self.local_types.get(expr.id, "any")

        # Like the Div -> float rule below, this assumes built-in operator
        # semantics; an overloaded __eq__ (NumPy, SQLAlchemy) can return
        # something else.
        if isinstance(expr, ast.Compare) or (
            isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not)
        ):
            return "bool"

        if isinstance(expr, ast.BoolOp):
            # `and`/`or` return one of their operands, not a coerced bool.
            operand_types = {self.infer_expr_type(v) for v in expr.values}
            return operand_types.pop() if len(operand_types) == 1 else "any"

        if isinstance(expr, ast.JoinedStr):
            return "str"

        if isinstance(expr, ast.BinOp):
            return self._infer_binop_type(expr)

        if isinstance(expr, ast.Call):
            return self._infer_call_type(expr)

        if isinstance(expr, ast.Attribute):
            return self._infer_attribute_type(expr)

        return "any"

    def get_annotation_type(self, annotation: Any) -> str:
        """
        Translates an AST annotation node into a human-readable type string.
        Supports PEP 604 (|) and PEP 585 (list[int]).

        Args:
            annotation (Any): The annotation node (ast.Name, ast.Subscript, etc.).

        Returns:
            str: The type string.
        """
        if isinstance(annotation, ast.Name):
            return annotation.id

        if isinstance(annotation, ast.Constant):
            if annotation.value is None:
                return "None"
            if isinstance(annotation.value, str):
                # A quoted forward reference (e.g. `-> "ClassName"`, PEP
                # 484's way of naming a type not yet defined at the
                # annotation's point in the source -- the standard
                # fluent-builder self-return pattern, among others). The
                # string literal *is* the type name, a fact straight from
                # the source, not a shape to fall through to "any" on.
                return annotation.value
            return "any"

        if isinstance(annotation, ast.Attribute):
            value_id = self.get_annotation_type(annotation.value)
            return f"{value_id}.{annotation.attr}"

        if isinstance(annotation, ast.Subscript):
            base_type = self.get_annotation_type(annotation.value)
            # Python 3.9+ uses Slice for index in some cases, but 3.10+ simplified it
            index = annotation.slice
            if isinstance(index, ast.Index):  # Older Python
                index = index.value

            # Handle Tuple/List of types inside subscript
            if isinstance(index, ast.Tuple):
                inner_types = ", ".join(
                    self.get_annotation_type(elt) for elt in index.elts
                )
                return f"{base_type}[{inner_types}]"

            inner_type = self.get_annotation_type(index)
            return f"{base_type}[{inner_type}]"

        if isinstance(annotation, ast.BinOp):
            if isinstance(annotation.op, ast.BitOr):  # PEP 604: int | str
                left = self.get_annotation_type(annotation.left)
                right = self.get_annotation_type(annotation.right)
                return f"Union[{left}, {right}]"

        return "any"

    def _infer_binop_type(self, node: ast.BinOp) -> str:
        """
        Infers the result of a binary operation.

        Args:
            node (ast.BinOp): The binary operation node.

        Returns:
            str: The inferred type.
        """
        left = self.infer_expr_type(node.left)
        right = self.infer_expr_type(node.right)

        if left == "float" or right == "float":
            return "float"

        if isinstance(node.op, ast.Div):
            return "float"

        if left != "any":
            return left
        return right

    def _infer_call_type(self, node: ast.Call) -> str:
        """
        Infers return type from a function call (basic heuristic).

        Args:
            node (ast.Call): The call node to analyze.

        Returns:
            str: The inferred return type.
        """
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in {"int", "float", "str", "list", "dict", "set", "bool"}:
                return name
            if name == "len":
                return "int"
            if name in _BOOL_BUILTINS:
                return "bool"

        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
            and node.func.attr in _STR_RETURNING_STR_METHODS
        ):
            return "str"

        if isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            if node.func.value.id == "math":
                return "float"

        return "any"

    def _infer_attribute_type(self, node: ast.Attribute) -> str:
        """
        Infers type of an attribute access.

        Args:
            node (ast.Attribute): The attribute node.

        Returns:
            str: The inferred type.
        """
        if isinstance(node.value, ast.Name):
            if node.value.id == "math" and node.attr in {"pi", "e", "tau"}:
                return "float"
        return "any"
