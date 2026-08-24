import ast
import os
import sys
import pytest
import logging

# Add parent directory to path to allow importing from PyCodeCommenter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

logging.disable(logging.CRITICAL)

@pytest.fixture
def commenter():
    return PyCodeCommenter()

def test_empty_string(commenter):
    """Test with an empty string."""
    commenter.from_string("")
    docstrings = commenter.generate_docstrings()
    assert docstrings == []
    assert commenter.get_patched_code() == ""

def test_syntax_error(commenter):
    """Test with a syntax error in the code."""
    code = "def invalid_syntax(:"
    commenter.from_string(code)
    docstrings = commenter.generate_docstrings()
    assert docstrings == []
    assert commenter.get_patched_code() == code

def test_unicode_handling(commenter):
    """Test with Unicode characters in function names and strings."""
    code = """def 世界_function(name="世界"):
    return f"Hello {name} 🚀"
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert 'Args:' in patched
    assert 'Returns:' in patched
    assert '世界' in patched
    assert '🚀' in patched

def test_large_file(commenter):
    """Test with a large number of functions and lines."""
    functions = []
    for i in range(200):
        functions.append(f"def func_{i}(a: int, b: int) -> int:\n    return a + b + {i}")
    large_code = "\n\n".join(functions)
    commenter.from_string(large_code)
    docstrings = commenter.generate_docstrings()
    assert len(docstrings) == 200
    patched = commenter.get_patched_code()
    assert "func_199" in patched
    assert "Args:" in patched

def test_multiline_signature_docstring_placement(commenter):
    """Regression test for the 'multi-line signature corruption' item in
    Future Work/Vulnerabilties.md (Question 2, first CRITICAL issue).

    The audit claims get_patched_code() inserts the docstring using
    node.body[0].lineno, and that for a multi-line signature this lands
    inside the signature's continuation lines rather than after it -
    corrupting the file. This does not reproduce: Python's ast module
    resolves body[0].lineno to wherever the first real statement actually
    is, regardless of signature length (verified directly against the
    audit's own example, including a trailing comment on an argument
    line). This test locks in the current, correct behavior as a
    regression safety net.
    """
    code = (
        "def very_long_function_name(\n"
        "    argument_one: str,\n"
        "    argument_two: int,     # <-- lineno of body[0] is THIS line\n"
        "    argument_three: bool,\n"
        ") -> dict:\n"
        "    return {}\n"
    )
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    # Must remain syntactically valid; a corrupted signature would raise
    # SyntaxError here.
    tree = ast.parse(patched)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert func.name == "very_long_function_name"
    assert [a.arg for a in func.args.args] == [
        "argument_one", "argument_two", "argument_three",
    ]

    # Docstring must be the first body statement, and the original body
    # statement must survive intact right after it - not swallowed,
    # duplicated, or shifted into the signature.
    assert ast.get_docstring(func) is not None
    real_stmts = func.body[1:]
    assert len(real_stmts) == 1
    assert ast.unparse(real_stmts[0]) == "return {}"

def test_multi_function_no_line_shift_corruption(commenter):
    """Regression test for the 'line-shift insertion bug' item in
    Future Work/Vulnerabilties.md (Question 2, second CRITICAL issue).

    The audit claims that when get_patched_code() applies multiple
    insertions/replacements to the same file, line-number arithmetic on
    the mutable lines[] list can cause an edit to land on the wrong line.
    This does not reproduce: dumping the raw (start, end, content) changes
    computed for a file mixing insertions, existing-docstring replacements,
    multi-line signatures, and nested classes shows every change lands on a
    distinct, correctly source-ordered line, and reverse-order processing
    (as used here) is the standard-correct technique for this exact
    problem. This test locks in the current, correct behavior as a
    regression safety net by verifying each function's real body statement
    survives unchanged and un-shifted after patching.
    """
    code = '''def a(x, y):
    """Old doc for a."""
    return x

def b(
    x,
    y) -> int:
    return x + y

class Outer:
    """Old outer doc."""

    def m1(self, x):
        return x

    class Inner:
        def m2(
            self,
            val: int,
        ):
            """Old inner doc that is way too short."""
            return val

def c(x, y, z):
    return x

def d(
    a,
    b,
    c,
):
    """Existing docstring for d that will be regenerated because it is bad."""
    return a
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    # Must remain syntactically valid; a line-shift bug would typically
    # produce a SyntaxError or misplace a statement inside another scope.
    tree = ast.parse(patched)

    def first_real_stmt(node):
        body = node.body
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        return ast.unparse(body[0]) if body else None

    functions = {}

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            functions[node.name] = first_real_stmt(node)
            self.generic_visit(node)

    _Collector().visit(tree)

    assert functions == {
        "a": "return x",
        "b": "return x + y",
        "m1": "return x",
        "m2": "return val",
        "c": "return x",
        "d": "return a",
    }

def test_get_patched_code_preserves_comments(commenter):
    """Phase 3 deliverable: verify whether comments in the source file
    survive get_patched_code() now that it is libcst-based.

    Result: yes, they do. libcst is a lossless concrete syntax tree, and
    the patcher only replaces/inserts the specific docstring statement for
    each function/class - it never reconstructs surrounding code - so
    every comment shown below (module-level, inline-on-an-import,
    trailing-on-a-def-line, a standalone comment inside a body, an inline
    comment on a statement, and a trailing comment on a one-liner
    definition) is asserted to survive verbatim.
    """
    code = '''# Module comment
import os  # inline import comment

def foo(x, y):  # trailing comment on def line
    # leading comment inside body
    z = x + y  # inline comment on statement
    return z  # trailing return comment

def bar(): return 1  # trailing comment on one-liner

class C:
    # comment before method
    def method(self):
        return 1
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    ast.parse(patched)  # must remain syntactically valid

    for expected_comment in [
        "# Module comment",
        "# inline import comment",
        "# trailing comment on def line",
        "# leading comment inside body",
        "# inline comment on statement",
        "# trailing return comment",
        "# trailing comment on one-liner",
        "# comment before method",
    ]:
        assert expected_comment in patched, f"comment lost: {expected_comment!r}"

def test_type_preserved_from_existing_docstring_when_unannotated(commenter):
    """Regression test for Phase 6 bug 6a: a parameter's documented type
    must not be silently downgraded to 'any' when static inference has
    nothing to work with (no annotation on an untyped parameter).
    """
    code = '''def with_doc(x):
    """Custom summary.

    Args:
        x (int): custom description that should survive.
    """
    return None
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "x (int): custom description that should survive." in patched
    assert "x (any)" not in patched

def test_static_annotation_wins_over_stale_docstring_type(commenter):
    """6a precedence: a real type annotation must always beat a stale
    type documented in an existing docstring.
    """
    code = '''def with_doc(x: str):
    """Custom summary.

    Args:
        x (int): stale type from a prior edit.
    """
    return None
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "x (str):" in patched
    assert "x (int):" not in patched

def test_numpy_docstring_not_duplicated_on_regeneration(commenter):
    """Regression test for Phase 6 bug 6b, using config.py's real
    load_config() signature+docstring verbatim. Before the fix, an
    unrecognized NumPy Returns section meant the whole body was folded
    into 'description', and a second, auto-generated Google-style
    Returns: section was appended - documenting the return value twice.
    """
    code = '''from typing import Dict, Any, Optional

def load_config(start_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration for PyCodeCommenter.

    Parameters
    ----------
    start_path: str | None, optional
        Directory to start the search from.  Defaults to the current working
        directory.

    Returns
    -------
    dict
        Parsed configuration dictionary.  Returns an empty dictionary if no
        ``.pycodecommenter.yaml`` file is discovered.

    Raises
    ------
    ConfigError
        If a config file is discovered but parsing fails.
    """
    return {}
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    ast.parse(patched)
    # The description text (not the bare identifier, which legitimately
    # appears once in the signature and once in the docstring even when
    # correct) must appear exactly once - proof there is no second,
    # auto-generated Args/Returns entry duplicating the original.
    assert patched.count("Directory to start the search from.") == 1
    assert patched.count("Parsed configuration dictionary.") == 1
    assert "start_path (Optional[str]): Directory to start the search from." in patched

def test_dunder_init_parameter_description_not_garbled(commenter):
    """Regression test for Phase 6 bug 6c, using ConfigError.__init__'s
    real (undocumented) signature from config.py.

    The parameter description that used to fall back to a
    "{Param} of the {function}" sentence derived from the dunder name is now
    a guess marker instead (Tier 1: guesses aren't presented as finished
    prose) -- so nothing derived from humanize_identifier('__init__') is
    rendered here at all any more. The negative assertions still guard
    against the original bug (a naive, non-dunder-aware humanize) resurfacing
    anywhere.
    """
    code = '''class ConfigError(Exception):
    """Raised when config parsing fails."""
    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "   init   " not in patched
    assert "of the   init  " not in patched
    assert "TODO(pycodecommenter): describe" in patched

def test_dunder_summary_not_garbled_for_non_init_dunders(commenter):
    """6c also affects the summary line for dunders other than __init__,
    which is separately special-cased.
    """
    code = '''class C:
    def __repr__(self):
        return "C()"
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert '"""  repr  .' not in patched
    assert '"""Repr.' in patched


# ---------------------------------------------------------------------------
# get_all_parameters() coverage: func_node.args.args alone is blind to
# posonlyargs, kwonlyargs, vararg, and kwarg, and to self.x = ... class
# attributes and class-level AnnAssign fields. These six tests mirror the
# named cases in scratch/docstring_generation_fixture.py.
# ---------------------------------------------------------------------------

def test_generator_function_gets_yields_not_returns(commenter):
    """A function with a yield is a generator; it should get a Yields
    section, not a Returns: None section (fixture case #4).
    """
    code = '''def iter_batches(items, batch_size=10):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Yields:" in patched
    assert "Returns:" not in patched


def test_yield_in_nested_function_not_attributed_to_outer(commenter):
    """A yield inside a nested def must not make the *outer* function look
    like a generator (the ast.walk nested-scope landmine called out for
    _get_return_type).
    """
    code = '''def make_batcher(batch_size):
    def batches(items):
        yield items[:batch_size]

    return batches
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    # Outer function returns a plain callable -- it must keep "Returns:".
    assert '"""Make batcher.' in patched
    outer_doc = patched.split('"""Make batcher.', 1)[1].split('"""', 1)[0]
    assert "Returns:" in outer_doc
    assert "Yields:" not in outer_doc
    # Inner function is the actual generator.
    assert '"""Batches.' in patched
    inner_doc = patched.split('"""Batches.', 1)[1].split('"""', 1)[0]
    assert "Yields:" in inner_doc


def test_keyword_only_params_appear_in_args(commenter):
    """Bare-`*` keyword-only parameters live in func_node.args.kwonlyargs,
    not func_node.args.args (fixture case #6).
    """
    code = '''def build_report(*, title, sections, verbose=False):
    return title
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    title (" in patched
    assert "    sections (" in patched
    assert "    verbose (" in patched
    assert "(default: False)" in patched
    assert "Args:\n    None." not in patched


def test_positional_only_params_appear_in_args(commenter):
    """Params before a bare `/` live in func_node.args.posonlyargs, not
    func_node.args.args (fixture case #7).
    """
    code = '''def clamp(value, low, /, high=1.0):
    return max(low, min(value, high))
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    value (" in patched
    assert "    low (" in patched
    assert "    high (" in patched


def test_varargs_and_kwargs_appear_in_args(commenter):
    """*args/**kwargs live in func_node.args.vararg/kwarg, not
    func_node.args.args (fixture case #8).
    """
    code = '''def dispatch_event(event_name, *args, **kwargs):
    print(event_name, args, kwargs)
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    *args (tuple):" in patched
    assert "    **kwargs (dict):" in patched


def test_class_attributes_include_self_assign_and_exclude_cls(commenter):
    """self.x = ... assignments beyond __init__'s own parameters must be
    picked up as attributes, and a @classmethod's `cls` must not be
    documented as an Args entry (fixture case #10).
    """
    code = '''class OrderProcessor:
    def __init__(self, customer_id, items):
        self.customer_id = customer_id
        self.items = items
        self.total = 0.0

    @classmethod
    def empty(cls, customer_id):
        return cls(customer_id, [])
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    total (float):" in patched
    empty_doc = patched.split('"""Empty.', 1)[1].split('"""', 1)[0]
    assert "cls" not in empty_doc
    assert "    customer_id (" in empty_doc


def test_dataclass_without_explicit_init_gets_attributes(commenter):
    """A @dataclass with class-level annotated fields and no __init__ in
    source must still produce an Attributes section (fixture case #11).
    """
    code = '''from dataclasses import dataclass

@dataclass
class Coordinates:
    latitude: float
    longitude: float
    label: str = "unnamed"
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Attributes:" in patched
    assert "    latitude (float):" in patched
    assert "    longitude (float):" in patched
    assert "    label (str):" in patched


# ---------------------------------------------------------------------------
# Tier 1: fact/guess boundary. Guessed content (no real signal to describe a
# parameter/function/attribute/method from) is marked with the TODO(...)
# guess marker instead of being presented as a finished sentence; facts
# (AST-derived types/names/defaults, parameter_descriptions.py overrides,
# and preserved existing docstring text) are filled in silently.
# ---------------------------------------------------------------------------

def test_generated_output_with_unresolved_guesses_fails_own_validator(commenter):
    """The generator's own guess markers must trip validator.py's existing
    placeholder check -- closing the self-contradiction where generated
    output used to fail the generator's own placeholder blacklist silently
    (the blacklist includes "Description of", which the old filler text
    always contained, but nothing surfaced that failure to the user).
    """
    code = '''def calculate_discount(price, rate=0.1):
    return price * (1 - rate)
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    validator = PyCodeCommenter()
    validator.from_string(patched)
    report = validator.validate()

    placeholder_issues = [
        i for i in report.issues
        if i.category == "quality" and "Placeholder text 'TODO'" in i.message
    ]
    assert placeholder_issues, "generated guesses should trip the placeholder check"


def test_legitimate_lightweight_inference_stays_unmarked(commenter):
    """Name-pattern and type-hint based inference (infer_description's rules
    1-3) are still presented as real descriptions, not the guess marker --
    only the final generic fallback (rule 4) is a guess.
    """
    code = '''def read_file(file_path: str, amount: int):
    return open(file_path).read()
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    args_section = patched.split("Args:", 1)[1].split("Returns:", 1)[0]
    assert "TODO(pycodecommenter): describe" not in args_section
    assert "Path to the" in args_section  # file_path name-pattern rule
    assert "int value" in args_section  # amount type-hint rule


def test_static_override_and_preserved_text_stay_unmarked(commenter):
    """A parameter_descriptions.py static override is a fact (someone
    deliberately wrote it), and preserved text from an existing docstring is
    the author's real words -- neither should ever be replaced by the guess
    marker.
    """
    code = '''def calculate_area(length, width):
    """Calculate the area of a rectangle.

    Args:
        length (float): The length, already documented by hand.
    """
    return length * width
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    args_section = patched.split("Args:", 1)[1].split("Returns:", 1)[0]
    assert "TODO(pycodecommenter): describe" not in args_section
    assert "Width of the rectangle." in args_section  # static override for width
    assert "The length, already documented by hand." in args_section  # preserved
