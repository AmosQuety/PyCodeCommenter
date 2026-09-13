import os
import sys
import logging
import pytest
import ast

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyCodeCommenter.type_analyzer import TypeAnalyzer  # noqa: E402

logging.disable(logging.CRITICAL)


@pytest.fixture
def analyzer():
    return TypeAnalyzer()


def test_constant(analyzer):
    assert analyzer.infer_expr_type(ast.parse("1").body[0].value) == "int"


def test_string(analyzer):
    assert analyzer.infer_expr_type(ast.parse("'s'").body[0].value) == "str"


def test_list(analyzer):
    assert analyzer.infer_expr_type(ast.parse("[]").body[0].value) == "list"


def test_union_annotation(analyzer):
    ann = ast.parse("x: int | str").body[0].annotation
    assert analyzer.get_annotation_type(ann) == "Union[int, str]"


def test_generic_annotation(analyzer):
    ann = ast.parse("x: list[int]").body[0].annotation
    assert analyzer.get_annotation_type(ann) == "list[int]"


def test_string_forward_reference_annotation_resolves_to_named_type(analyzer):
    """A quoted forward reference (`-> "ClassName"`, PEP 484's way of naming
    a type not yet defined at the annotation's point in the source -- the
    standard fluent-builder self-return pattern, among others) is a fact
    straight from the source and must resolve to that class name, not fall
    through to "any" the way an arbitrary ast.Constant would.
    """
    ann = ast.parse('def f() -> "PyCodeCommenter": ...').body[0].returns
    assert analyzer.get_annotation_type(ann) == "PyCodeCommenter"


def test_string_forward_reference_inside_generic_resolves_to_named_type(analyzer):
    """The same forward-reference resolution must apply recursively inside
    a subscripted annotation (e.g. Optional["ClassName"]), not just at the
    top level."""
    ann = ast.parse('x: Optional["Coordinates"]').body[0].annotation
    assert analyzer.get_annotation_type(ann) == "Optional[Coordinates]"


def test_none_constant_annotation_still_resolves_to_none(analyzer):
    """Regression guard: widening ast.Constant handling to cover string
    forward references must not disturb the pre-existing `-> None` case."""
    ann = ast.parse("def f() -> None: ...").body[0].returns
    assert analyzer.get_annotation_type(ann) == "None"
