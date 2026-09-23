import ast
import os
import sys
import pytest
import logging

# Add parent directory to path to allow importing from PyCodeCommenter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
    assert "Args:" in patched
    assert "Returns:" in patched
    assert "世界" in patched
    assert "🚀" in patched


def test_large_file(commenter):
    """Test with a large number of functions and lines."""
    functions = []
    for i in range(200):
        functions.append(
            f"def func_{i}(a: int, b: int) -> int:\n    return a + b + {i}"
        )
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
        "argument_one",
        "argument_two",
        "argument_three",
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
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
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
    code = """# Module comment
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
"""
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
    # The NumPy style is kept (not converted to Google style).
    assert "    start_path : Optional[str], optional\n" in patched
    assert "Args:" not in patched
    assert commenter.from_string(patched).get_patched_code() == patched


def test_numpy_raises_section_not_corrupted_on_regeneration(commenter):
    """Regression test for AUDIT_REPORT.md §1.3, using config.py's real
    load_config() docstring verbatim, this time with a real raise in the
    body (the prior test above doesn't have one, so it never exercised
    this path).

    Before the fix, an unrecognized NumPy Raises section was folded into
    `description`, producing a malformed, un-styled "Raises\\nConfigError\\n
    ..." block floating above Args:/Returns: -- and, once Tier 2a's real
    Raises: generation existed, a *second*, correct, freshly-generated
    Raises: section describing the exact same exception, so the exception
    ended up documented twice, once correctly and once malformed.
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
    raise ConfigError("bad")
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    ast.parse(patched)

    # Exactly one Raises section, still in the author's NumPy style, naming
    # the exception exactly once within the docstring -- no leftover block
    # and no second, Google-style copy. A second "ConfigError" is expected
    # and correct: the `raise ConfigError(...)` statement below the
    # docstring.
    assert patched.count("Raises\n    ------") == 1
    assert "Raises:" not in patched
    docstring_only = patched.split('"""', 2)[1]
    assert docstring_only.count("ConfigError") == 1
    assert "If a config file is discovered but parsing fails." in docstring_only
    # Sections keep NumPy's order: Parameters, Returns, Raises.
    assert (
        patched.index("Parameters\n")
        < patched.index("Returns\n")
        < patched.index("Raises\n")
    )


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
    code = """class C:
    def __repr__(self):
        return "C()"
"""
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
    code = """def iter_batches(items, batch_size=10):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Yields:" in patched
    assert "Returns:" not in patched


def test_function_that_raises_gets_raises_section(commenter):
    """A function with a `raise SomeError(...)` in its own body must get a
    Raises: section naming the exception class (fixture case #3, and the
    generator's own generated output used to trip its own validator's
    "raises exceptions but has no Raises section" warning)."""
    code = """def parse_positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{value} must not be negative")
    return parsed
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Raises:" in patched
    raises_section = patched.split("Raises:", 1)[1]
    assert "ValueError:" in raises_section

    validator = PyCodeCommenter()
    validator.from_string(patched)
    report = validator.validate()
    raises_warnings = [i for i in report.issues if "has no Raises section" in i.message]
    assert not raises_warnings


def test_bare_reraise_and_preconstructed_exception_get_no_raises_entry(commenter):
    """A bare `raise` (re-raise) and `raise err` (an already-constructed
    instance) can't have their exception class read off the raise site
    without data-flow analysis -- both must be skipped rather than guessed.
    """
    code = """def f(x):
    try:
        pass
    except Exception:
        raise
    err = ValueError("already built")
    raise err
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Raises:" not in patched


def test_raise_via_module_attribute_uses_short_exception_name(commenter):
    """`raise module.MyError(...)` must render as just "MyError" in
    Raises: (matching how a Raises section is conventionally written),
    not the fully qualified "module.MyError"."""
    code = """def f(x):
    if x:
        raise exceptions.MyError("bad")
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    raises_section = patched.split("Raises:", 1)[1].split('"""', 1)[0]
    assert "MyError:" in raises_section
    assert "exceptions.MyError" not in raises_section


def test_raise_in_nested_function_not_attributed_to_outer(commenter):
    """A raise inside a nested def must not make the *outer* function look
    like it raises that exception (same scope-boundary concern as yield/
    return)."""
    code = """def outer(x):
    def inner():
        raise KeyError("nested")
    return inner
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    outer_doc = patched.split('"""Outer.', 1)[1].split('"""', 1)[0]
    assert "Raises:" not in outer_doc
    assert "KeyError" in patched  # still present, just on inner's own docstring


def test_yield_in_nested_function_not_attributed_to_outer(commenter):
    """A yield inside a nested def must not make the *outer* function look
    like a generator (the ast.walk nested-scope landmine called out for
    _get_return_type).
    """
    code = """def make_batcher(batch_size):
    def batches(items):
        yield items[:batch_size]

    return batches
"""
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
    code = """def build_report(*, title, sections, verbose=False):
    return title
"""
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
    code = """def clamp(value, low, /, high=1.0):
    return max(low, min(value, high))
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    value (" in patched
    assert "    low (" in patched
    assert "    high (" in patched


def test_varargs_and_kwargs_appear_in_args(commenter):
    """*args/**kwargs live in func_node.args.vararg/kwarg, not
    func_node.args.args (fixture case #8).
    """
    code = """def dispatch_event(event_name, *args, **kwargs):
    print(event_name, args, kwargs)
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "    *args (tuple):" in patched
    assert "    **kwargs (dict):" in patched


def test_class_attributes_include_self_assign_and_exclude_cls(commenter):
    """self.x = ... assignments beyond __init__'s own parameters must be
    picked up as attributes, and a @classmethod's `cls` must not be
    documented as an Args entry (fixture case #10).
    """
    code = """class OrderProcessor:
    def __init__(self, customer_id, items):
        self.customer_id = customer_id
        self.items = items
        self.total = 0.0

    @classmethod
    def empty(cls, customer_id):
        return cls(customer_id, [])
"""
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
    code = """from dataclasses import dataclass

@dataclass
class Coordinates:
    latitude: float
    longitude: float
    label: str = "unnamed"
"""
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
# (AST-derived types/names/defaults, and preserved existing docstring text)
# are filled in silently.
# ---------------------------------------------------------------------------


def test_generated_output_with_unresolved_guesses_fails_own_validator(commenter):
    """The generator's own guess markers must trip validator.py's existing
    placeholder check -- closing the self-contradiction where generated
    output used to fail the generator's own placeholder blacklist silently
    (the blacklist includes "Description of", which the old filler text
    always contained, but nothing surfaced that failure to the user).
    """
    code = """def calculate_discount(price, rate=0.1):
    return price * (1 - rate)
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    validator = PyCodeCommenter()
    validator.from_string(patched)
    report = validator.validate()

    placeholder_issues = [
        i
        for i in report.issues
        if i.category == "quality" and "Placeholder text 'TODO'" in i.message
    ]
    assert placeholder_issues, "generated guesses should trip the placeholder check"


def test_already_complete_docstring_gets_no_phantom_description(commenter):
    """Regression test for the PyPI-dogfooding audit's #1 finding: merging
    into an already-complete Google-style docstring (summary + Args +
    Returns, no separate description paragraph) must not inject a
    TODO(pycodecommenter) placeholder paragraph that was never asked for.
    The output must reproduce the original byte-for-byte.
    """
    code = '''def slugify(text: str) -> str:
    """Convert text into a URL-friendly slug.

    Args:
        text (str): The text to slugify.

    Returns:
        str: The lowercased, hyphen-joined slug.
    """
    return text.lower()
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "TODO(pycodecommenter)" not in patched
    assert patched == code


def test_fresh_function_gets_no_phantom_description_either(commenter):
    """A function with no existing docstring at all still gets no free-text
    description paragraph: the name-derived summary immediately above it is
    already an honest best-effort, and a second "TODO: describe" paragraph
    duplicating that same lack of information is noise, not new honesty.
    Per-field placeholders (Args/Returns, where the tool genuinely cannot
    infer more than a bare type) are unaffected and still appear.
    """
    code = """def calculate_discount(price, rate=0.1):
    return price * (1 - rate)
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    summary_to_args = patched.split('"""Calculate discount.', 1)[1].split("Args:", 1)[0]
    assert "TODO(pycodecommenter)" not in summary_to_args
    assert "TODO(pycodecommenter): describe" in patched  # still present in Args/Returns


def test_multiline_hand_wrapped_summary_preserved_as_one_summary(commenter):
    """Regression test for the audit's #2 finding: a hand-wrapped summary
    sentence spanning multiple physical lines, with no blank line between
    them, must stay one summary -- not get chopped at the wrap point into a
    summary plus a spurious, mid-sentence description paragraph.
    """
    code = '''def _walk_until(node, boundary_types):
    """Shared traversal for the two scope-bounded walkers below: yields every
    descendant of *node*, without descending past a node whose type is in
    *boundary_types*.

    Args:
        node: The node whose descendants should be walked.
        boundary_types: AST node types to yield but not expand into.
    """
    pass
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    summary_line = patched.splitlines()[1]
    assert summary_line == (
        '    """Shared traversal for the two scope-bounded walkers below: '
        "yields every descendant of *node*, without descending past a node "
        "whose type is in *boundary_types*."
    )
    assert (
        "descendant of *node*" not in patched.split("\n\n", 1)[1].split("Args:", 1)[0]
    )


def test_defaulted_parameter_description_stable_across_regeneration():
    """Regression test for the idempotency bug in
    Another_Test_PyCodeCommenter/Feedback/IDEMPOTENCY_BUG.md: generation
    unconditionally appends " (default: ...)" to a parameter's description,
    but a re-parsed docstring stores that suffix as part of the "existing"
    description too -- so regenerating used to compound another copy of the
    suffix onto the same line on every single pass, without bound.

    A single before/after diff isn't enough here: the bug doesn't show up
    until the *second* pass, and without this test it could easily reappear
    on only the third or fourth pass while a two-pass check stayed green.
    Regenerates 4 times and asserts every pass after the first is
    byte-identical to it.
    """
    code = (
        "def calculate_discount(price: float, rate: float = 0.1) -> float:\n"
        "    return price * (1 - rate)\n"
    )
    passes = []
    out = code
    for _ in range(4):
        out = PyCodeCommenter().from_string(out).get_patched_code()
        passes.append(out)

    assert "rate (float): float value. (default: 0.1)" in passes[0]
    for i in range(1, 4):
        assert passes[i] == passes[0], f"pass {i + 1} diverged from pass 1"
    # The specific compounding shape from the bug report must never appear.
    assert "(default: 0.1). (default: 0.1)" not in passes[-1]


def test_stale_default_value_does_not_compound_when_default_changes():
    """A narrower gap in the fix above: _strip_own_default_annotation used
    to only strip a suffix matching the parameter's *current* default, so
    editing a default in source between `generate` runs (a normal
    workflow: change a default, forget to touch the docstring, rerun the
    tool to fix it) left the stale suffix in place -- the append step then
    added a second, current one on top of it, e.g. "(default: 0.1).
    (default: 0.2)". The fix strips any trailing "(default: ...)" suffix
    unconditionally, since the append immediately below always re-adds the
    correct, current one regardless of what was stripped.
    """
    code_v1 = (
        "def calculate_discount(price: float, rate: float = 0.1) -> float:\n"
        "    return price * (1 - rate)\n"
    )
    pass1 = PyCodeCommenter().from_string(code_v1).get_patched_code()
    assert "rate (float): float value. (default: 0.1)" in pass1

    # Simulate a source edit: the default changes, the docstring doesn't.
    edited = pass1.replace("rate: float = 0.1", "rate: float = 0.2")
    pass2 = PyCodeCommenter().from_string(edited).get_patched_code()

    rate_line = [
        line for line in pass2.splitlines() if line.strip().startswith("rate ")
    ][0]
    assert rate_line.endswith("(default: 0.2)")
    assert rate_line.count("(default:") == 1
    assert "0.1" not in rate_line


def test_niladic_function_none_return_stable_across_regeneration():
    """Regression test for the second idempotency-bug instance: a
    niladic/void function's special-cased "Returns:\\n    None.\\n" sentence
    has no "type: " prefix for the existing-description merge logic to
    recognize, so a re-parsed docstring treated the bare "None." as real
    preserved text and re-wrapped it as "None: None." on the very next
    regeneration pass.

    Regenerates 4 times and asserts every pass after the first is
    byte-identical to it -- the duplication only appears starting on pass 2,
    so a single before/after diff would miss a regression here too.
    """
    code = "def refresh_cache() -> None:\n    pass\n"
    passes = []
    out = code
    for _ in range(4):
        out = PyCodeCommenter().from_string(out).get_patched_code()
        passes.append(out)

    assert "Returns:\n        None.\n" in passes[0]
    for i in range(1, 4):
        assert passes[i] == passes[0], f"pass {i + 1} diverged from pass 1"
    assert "None: None." not in passes[-1]


def test_stale_none_return_resets_when_function_starts_returning_a_value():
    """The "None." recognition above must not blindly preserve a stale
    Returns: section forever: if a previously-void function is edited to
    actually return a value, the old "None." text must be discarded in
    favor of a fresh description for the new, real return type -- not
    compounded into "int: None."."""
    stale_doc = '''def f():
    """F.

    Args:
        None.

    Returns:
        None.
    """
    return 42
'''
    commenter = PyCodeCommenter()
    commenter.from_string(stale_doc)
    patched = commenter.get_patched_code()
    assert "Returns:\n        int: TODO(pycodecommenter): describe" in patched
    assert "None." not in patched.split("Returns:", 1)[1]


def test_legitimate_lightweight_inference_stays_unmarked(commenter):
    """Name-pattern and type-hint based inference (infer_description's rules
    1-3) are still presented as real descriptions, not the guess marker --
    only the final generic fallback (rule 4) is a guess.
    """
    code = """def read_file(file_path: str, amount: int):
    return open(file_path).read()
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    args_section = patched.split("Args:", 1)[1].split("Returns:", 1)[0]
    assert "TODO(pycodecommenter): describe" not in args_section
    assert "Path to the" in args_section  # file_path name-pattern rule
    assert "int value" in args_section  # amount type-hint rule


def test_preserved_text_stays_unmarked(commenter):
    """Preserved text from an existing docstring is the author's real
    words -- it must never be replaced by the guess marker, even when a
    sibling parameter in the same function has nothing to go on and
    correctly gets the guess marker itself.
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
    assert "The length, already documented by hand." in args_section  # preserved
    assert "TODO(pycodecommenter): describe" in args_section  # width: no signal
    assert "The length, already documented by hand." in args_section  # preserved


def test_negative_default_value_rendered_correctly(commenter):
    """A negative-number default parses as UnaryOp(USub, Constant), not a
    single Constant -- _get_default_value must not fall back to "unknown"
    for it.
    """
    code = """def clamp(value, floor=-1, ceiling=+1):
    return max(floor, min(value, ceiling))
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "(default: -1)" in patched
    assert "(default: +1)" in patched
    assert "(default: unknown)" not in patched


def test_nested_class_self_attr_not_attributed_to_outer(commenter):
    """A `self.x = ...` assignment inside a class nested within __init__
    belongs to the nested class's own instance -- it must not be
    misattributed to the outer class's Attributes section.
    """
    code = """class Outer:
    def __init__(self):
        self.real_attr = 1

        class Inner:
            def __init__(self):
                self.fake_attr_for_outer = 2
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    outer_doc = patched.split('"""Outer class.', 1)[1].split('"""', 2)[0]
    assert "real_attr" in outer_doc
    assert "fake_attr_for_outer" not in outer_doc


def test_nested_closure_self_attr_still_found(commenter):
    """Unlike a nested class, a nested closure shares the enclosing
    __init__'s own `self` -- a self.x = ... assignment inside it is a real
    instance attribute and must still be picked up.
    """
    code = """class Widget:
    def __init__(self):
        self.value = 0

        def on_event(evt):
            self.value = evt.value

        self._handler = on_event
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    outer_doc = patched.split('"""Widget class.', 1)[1].split('"""', 2)[0]
    assert "value" in outer_doc
    assert "_handler" in outer_doc


def test_class_attribute_types_match_init_args_section(commenter):
    """The Attributes section's type inference must go through the same
    get_all_parameters()/exclude_self_cls() primitive as the Args section,
    so keyword-only params and **kwargs get the same (correct) type in
    both places instead of falling back to "any" in Attributes only.
    """
    code = """class Config:
    def __init__(self, *, host: str, port: int = 8080, **extra):
        self.host = host
        self.port = port
        self.extra = extra
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    attrs_section = patched.split("Attributes:", 1)[1].split('"""', 1)[0]
    assert "host (str)" in attrs_section
    assert "port (int)" in attrs_section
    assert "extra (dict)" in attrs_section


def test_class_attributes_get_real_inference_not_unconditional_guess_marker(commenter):
    """Attributes: descriptions must go through the same infer_description()
    pipeline Args: already uses -- a name/type pattern that would produce a
    real description for a parameter must produce the same real description
    for an attribute, not an unconditional TODO. An attribute with no
    matching name/type pattern must still correctly get the guess marker.
    """
    code = """class OrderProcessor:
    def __init__(self, customer_id: str, items: list):
        self.customer_id = customer_id
        self.items = items
        self.total = 0.0
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    attrs_section = patched.split("Attributes:", 1)[1].split("\n\n", 1)[0]
    assert "customer_id (str): Unique identifier for the customer." in attrs_section
    assert "items (list): List of items." in attrs_section
    # total's type (float) has a generic-but-real fallback -- not a guess.
    assert "total (float): float value." in attrs_section
    assert "TODO(pycodecommenter)" not in attrs_section


def test_property_accessor_trio_not_listed_as_methods(commenter):
    """AUDIT_REPORT.md §1.8 listed a property's getter/setter/deleter three
    times under Methods:. Methods: is no longer generated at all (see
    test_merge_preservation.py), so no accessor can be listed, once or
    three times."""
    code = """class Box:
    def __init__(self):
        self._value = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v

    @value.deleter
    def value(self):
        del self._value
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "Methods:" not in patched
    assert "value()" not in patched


# ---------------------------------------------------------------------------
# Module-level docstring generation (AUDIT_REPORT.md §2) -- opt-in only via
# include_module_docstrings, since unlike a missing function/class
# docstring, a missing module docstring would otherwise touch the output of
# nearly every input.
# ---------------------------------------------------------------------------


def test_module_docstrings_off_by_default():
    """The default constructor must not add a module docstring -- this is
    opt-in, unlike every other kind of docstring this tool generates, since
    it would otherwise change the output of nearly every existing input
    (any file/snippet with no module docstring already)."""
    code = "def foo():\n    pass\n"
    commenter = PyCodeCommenter()
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert not patched.startswith('"""')


def test_module_docstring_generated_when_opted_in_and_missing():
    """Regression test for AUDIT_REPORT.md §2: a file with zero docstrings
    anywhere (module or otherwise) -- the main.py-shaped gap -- must get a
    module docstring when the caller opts in."""
    code = "def foo():\n    pass\n"
    commenter = PyCodeCommenter(include_module_docstrings=True)
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert patched.startswith('"""')
    assert patched.splitlines()[0] == '"""Module docstring.'


def test_module_docstring_uses_filename_when_available():
    """A module docstring generated via from_file has a real name signal
    (the file itself) to derive its summary from, unlike from_string."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "cache_utils.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("CACHE_SIZE = 100\n")
        commenter = PyCodeCommenter(include_module_docstrings=True)
        commenter.from_file(path)
        patched = commenter.get_patched_code()
        assert patched.startswith('"""Cache utils."""')


def test_module_with_existing_docstring_is_never_touched():
    """A module docstring is only ever generated when there is none at
    all -- unlike function/class docstrings, this tool never attempts to
    merge into an existing module docstring (see _generate_module_docstring
    for why: much more free-form prose, real risk of corrupting it for no
    benefit, since the actual gap is files with none at all)."""
    code = '''"""Already has a module docstring."""
def foo():
    pass
'''
    commenter = PyCodeCommenter(include_module_docstrings=True)
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert patched.startswith('"""Already has a module docstring."""')
    assert patched.count('"""Already has a module docstring."""') == 1


def test_module_docstring_lists_real_classes_and_functions():
    """A module's top-level classes/functions are real AST facts, costing
    nothing to include -- mirrors the Attributes:/Methods: pattern already
    used for classes, one level up."""
    code = """class Foo:
    pass


def bar():
    pass
"""
    commenter = PyCodeCommenter(include_module_docstrings=True)
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    module_doc = patched.split('"""', 2)[1]
    assert "Classes:\n    Foo" in module_doc
    assert "Functions:\n    bar" in module_doc


def test_empty_module_gets_no_docstring_even_when_opted_in():
    """A module with no body at all (blank/whitespace-only input) has
    nothing to describe -- must not get a docstring even with the flag on,
    matching the existing, already-tested behavior for a genuinely empty
    file."""
    commenter = PyCodeCommenter(include_module_docstrings=True)
    commenter.from_string("")
    assert commenter.get_patched_code() == ""


def test_module_docstring_does_not_disturb_leading_comment():
    """A leading module comment (e.g. main.py's own commented-out import)
    must stay above the newly inserted module docstring, not be swallowed
    or reordered."""
    code = "# a leading comment\nX = 1\n"
    commenter = PyCodeCommenter(include_module_docstrings=True)
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    lines = patched.splitlines()
    assert lines[0] == "# a leading comment"
    assert lines[1] == '"""Module docstring."""'


# ---------------------------------------------------------------------------
# AUDIT_REPORT.md §3 -- CRLF files must round-trip as CRLF, not be silently
# normalized to LF on every generation run.
# ---------------------------------------------------------------------------


def test_crlf_file_round_trips_as_crlf(commenter, tmp_path):
    """A CRLF source file must come out CRLF, including on lines the
    generator itself wrote -- not just the untouched ones -- so a
    documentation PR on such a file doesn't turn into a full-file
    line-ending diff."""
    path = tmp_path / "crlf_sample.py"
    path.write_bytes(b"def foo(x):\r\n    return x\r\n")
    commenter.from_file(str(path))
    patched = commenter.get_patched_code()
    assert "\r\n" in patched
    assert "\n" not in patched.replace("\r\n", "")


def test_lf_file_unaffected_by_crlf_handling(commenter):
    """The CRLF-preservation fix must not affect a normal LF file."""
    code = "def foo(x):\n    return x\n"
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert "\r" not in patched


# ---------------------------------------------------------------------------
# AUDIT_REPORT.md §5 -- an unexpected exception mid-generation must not
# silently discard a real, existing docstring in favor of a placeholder.
# ---------------------------------------------------------------------------


def test_function_generation_failure_preserves_existing_docstring(commenter):
    """Regression test for AUDIT_REPORT.md §5: a failure inside
    _generate_function_docstring must fall back to the original docstring,
    not the destructive '\"\"\"Error generating docstring.\"\"\"' placeholder."""
    from unittest.mock import patch
    from PyCodeCommenter.commenter import PyCodeCommenter as _PCC

    code = '''def foo(x):
    """An existing, hand-written docstring that must survive."""
    return x
'''
    commenter.from_string(code)
    with patch.object(_PCC, "_get_return_type", side_effect=RuntimeError("boom")):
        patched = commenter.get_patched_code()
    assert '"""An existing, hand-written docstring that must survive."""' in patched
    assert "Error generating docstring" not in patched


def test_function_generation_failure_with_no_existing_docstring_unchanged(commenter):
    """The fix above must not regress the no-docstring-to-preserve case:
    when there was nothing to fall back to, the placeholder is still used,
    same as before."""
    from unittest.mock import patch
    from PyCodeCommenter.commenter import PyCodeCommenter as _PCC

    code = "def bar(x):\n    return x\n"
    commenter.from_string(code)
    with patch.object(_PCC, "_get_return_type", side_effect=RuntimeError("boom")):
        patched = commenter.get_patched_code()
    assert '"""Error generating docstring."""' in patched


def test_class_generation_failure_preserves_existing_docstring(commenter):
    """Same fix, for _generate_class_docstring."""
    from unittest.mock import patch
    from PyCodeCommenter.commenter import PyCodeCommenter as _PCC

    code = '''class Foo:
    """An existing class docstring that must survive."""
    def method(self):
        pass
'''
    commenter.from_string(code)
    with patch.object(_PCC, "_get_class_attributes", side_effect=RuntimeError("boom")):
        patched = commenter.get_patched_code()
    assert '"""An existing class docstring that must survive."""' in patched


# ---------------------------------------------------------------------------
# The "Initialize the class." / "Initialize a new instance." boilerplate --
# the description no longer defaults to fixed boilerplate text on every
# constructor, consistent with every other function.
# ---------------------------------------------------------------------------


def test_init_no_longer_gets_boilerplate_description(commenter):
    """A fresh __init__ with no existing docstring keeps its recognizable
    "Initialize the class." summary, but no longer gets the identical
    "Initialize a new instance." description paragraph on every single
    constructor regardless of what the class does."""
    code = """class OrderProcessor:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert '"""Initialize the class.' in patched
    assert "Initialize a new instance." not in patched
