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
