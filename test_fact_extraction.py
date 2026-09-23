"""Facts the AST already contains, surfaced instead of left as TODO markers.

Every assertion here is about something readable straight off the source:
the condition guarding a `raise`, the type of a comparison, the expression a
boolean function returns. Where the source doesn't state a fact, the guess
marker must stay -- lowering the TODO count by guessing is a regression, not
progress (see Feedback/TIER2_TODO_REDUCTION.md in the audit notes).

The two fixtures at the bottom are the maintainer's own end-to-end samples:
the `ai_test_batch` files used to exercise --ai-draft, and a small service
class shaped like real application code.
"""

import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.inference import infer_description
from PyCodeCommenter.type_analyzer import TypeAnalyzer

logging.disable(logging.CRITICAL)

GUESS = "TODO(pycodecommenter)"


@pytest.fixture
def commenter():
    return PyCodeCommenter()


def _generate(code: str) -> str:
    return PyCodeCommenter().from_string(code).get_patched_code()


def _section(patched: str, header: str) -> str:
    return patched.split(f"{header}:\n", 1)[1].split('"""', 1)[0]


def _expr_type(source: str) -> str:
    import ast

    return TypeAnalyzer().infer_expr_type(ast.parse(source, mode="eval").body)


# ---------------------------------------------------------------------------
# Raises: conditions read off the code
# ---------------------------------------------------------------------------


def test_raise_guarded_by_top_level_if_states_the_condition():
    raises = _section(
        _generate("""def apply(discount):
    if discount < 0:
        raise ValueError("negative discount")
    return discount
"""),
        "Raises",
    )
    assert "ValueError: If `discount < 0`." in raises


def test_raise_in_else_branch_states_the_negated_condition():
    raises = _section(
        _generate("""def pick(x):
    if x in ALLOWED:
        return x
    else:
        raise KeyError(x)
"""),
        "Raises",
    )
    assert "KeyError: If `x in ALLOWED` is false." in raises


def test_raise_inside_except_names_the_caught_exceptions():
    raises = _section(
        _generate("""def load(path):
    try:
        return read(path)
    except (OSError, UnicodeError) as e:
        raise ConfigError(path) from e
"""),
        "Raises",
    )
    assert "ConfigError: If `OSError` or `UnicodeError` occurs." in raises


def test_unconditional_raise_is_always_raised():
    raises = _section(
        _generate("""def area(self):
    raise NotImplementedError()
"""),
        "Raises",
    )
    assert "NotImplementedError: Always." in raises


def test_top_level_raise_after_an_early_return_is_not_called_always():
    """Reaching the raise depends on the earlier `return` not firing, so
    "Always." would be false."""
    raises = _section(
        _generate("""def first(items):
    if items:
        return items[0]
    raise LookupError("empty")
"""),
        "Raises",
    )
    assert "LookupError: " + GUESS in raises


def test_same_exception_raised_under_two_conditions_lists_both():
    raises = _section(
        _generate("""def clamp(x):
    if x < 0:
        raise ValueError("low")
    if x > 10:
        raise ValueError("high")
    return x
"""),
        "Raises",
    )
    assert "ValueError: If `x < 0`, or if `x > 10`." in raises


@pytest.mark.parametrize(
    "body",
    [
        # Nested condition: the inner test alone is not the full condition.
        "    if a:\n        if b:\n            raise ValueError()\n",
        # elif: the condition also depends on the earlier branch failing.
        "    if a:\n        return 1\n    elif b:\n        raise ValueError()\n",
        # Inside a loop: the condition refers to a loop variable.
        "    for x in xs:\n        if x:\n            raise ValueError()\n",
        # Too long to be a readable condition.
        "    if some_long_name.attribute_one and another_long_name.attribute_two"
        " and third_value:\n        raise ValueError()\n",
    ],
)
def test_raise_condition_not_stated_when_not_exact(body):
    code = "def f(a, b, xs, some_long_name, another_long_name, third_value):\n" + body
    raises = _section(_generate(code), "Raises")
    assert "ValueError: " + GUESS in raises


def test_one_unknown_raise_site_keeps_the_marker_for_that_exception():
    """Stating only the known condition would read as the complete list."""
    raises = _section(
        _generate("""def f(a, xs):
    if a:
        raise ValueError()
    for x in xs:
        if x:
            raise ValueError()
"""),
        "Raises",
    )
    assert "ValueError: " + GUESS in raises


# ---------------------------------------------------------------------------
# Return types read off the return expression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr, expected",
    [
        ("n % 2 == 0", "bool"),
        ("a < b <= c", "bool"),
        ("x is None", "bool"),
        ("key in table", "bool"),
        ("not ready", "bool"),
        ("isinstance(x, int)", "bool"),
        ("hasattr(x, 'name')", "bool"),
        ("x > 0 and y > 0", "bool"),
        ("f'{name}!'", "str"),
        ("' '.join(words)", "str"),
        ("'{}-{}'.format(a, b)", "str"),
        # `or`/`and` return an operand, not a bool -- unknown operands stay unknown.
        ("value or default", "any"),
        ("'a,b'.split(',')", "any"),
    ],
)
def test_expression_type_inference(expr, expected):
    assert _expr_type(expr) == expected


def test_comparison_return_documents_bool_and_its_condition():
    returns = _section(_generate("def is_even(n):\n    return n % 2 == 0\n"), "Returns")
    assert "bool: True if `n % 2 == 0`, otherwise False." in returns


def test_bool_description_only_for_a_single_return():
    """Two return paths mean no single condition describes the result."""
    returns = _section(
        _generate("""def ok(x):
    if x is None:
        return False
    return x > 0
"""),
        "Returns",
    )
    assert returns.strip() == "bool: " + GUESS + ": describe"


def test_author_return_text_beats_derived_condition():
    code = '''def is_even(n):
    """Is even.

    Returns:
        bool: Whether n is even.
    """
    return n % 2 == 0
'''
    assert "bool: Whether n is even." in _generate(code)


# ---------------------------------------------------------------------------
# Name inference: whole-word matching only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("item_count", "Number of item."),
        ("num_retries", "Number of retries."),
        ("pageCount", "Number of page."),
    ],
)
def test_count_rule_matches_whole_words(name, expected):
    assert infer_description(param_name=name) == expected


@pytest.mark.parametrize(
    "name", ["discount", "account", "country", "enum_type", "list_of_users"]
)
def test_count_rule_ignores_substrings_inside_other_words(name):
    assert not infer_description(param_name=name).startswith("Number of")


def test_bare_count_does_not_produce_empty_phrase():
    assert infer_description(param_name="count", type_hint="int") == "int value."


def test_untyped_attribute_uses_same_any_spelling_as_args():
    patched = _generate("""class Service:
    def __init__(self, repo):
        self.repo = repo
""")
    assert "repo (Any):" in _section(patched, "Attributes")


# ---------------------------------------------------------------------------
# End-to-end fixtures
# ---------------------------------------------------------------------------

AI_TEST_BATCH = """def add(a, b):
    return a + b


def is_even(n):
    return n % 2 == 0


def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)


def reverse_words(sentence):
    return " ".join(sentence.split()[::-1])


def count_vowels(text):
    return sum(1 for ch in text.lower() if ch in "aeiou")


def truncate(text, max_length):
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
"""

INVOICE_SERVICE = """class InvoiceService:
    def __init__(self, repo, tax_rate: float = 0.18):
        self.repo = repo
        self.tax_rate = tax_rate

    def total_due(self, invoice_id: str, discount: float = 0.0) -> float:
        invoice = self.repo.get(invoice_id)
        if invoice is None:
            raise KeyError(invoice_id)
        if discount < 0:
            raise ValueError("negative discount")
        return invoice.amount * (1 + self.tax_rate) - discount

    def overdue(self, days):
        for inv in self.repo.all():
            if inv.age > days:
                yield inv
"""


def test_ai_test_batch_gains_types_it_can_prove():
    patched = _generate(AI_TEST_BATCH)
    assert "bool: True if `n % 2 == 0`, otherwise False." in patched
    reverse_doc = patched.split("def reverse_words", 1)[1].split('"""', 2)[1]
    assert "str: " + GUESS in reverse_doc
    # a + b of unknown operands: nothing provable, the marker stays.
    add_doc = patched.split("def add", 1)[1].split('"""', 2)[1]
    assert "Any: " + GUESS in add_doc


def test_ai_test_batch_todo_count_drops_only_by_facts():
    assert _generate(AI_TEST_BATCH).count(GUESS) == 13


def test_invoice_service_has_no_guessed_raises_or_methods():
    patched = _generate(INVOICE_SERVICE)
    assert "KeyError: If `invoice is None`." in patched
    assert "ValueError: If `discount < 0`." in patched
    assert "Methods:" not in patched
    assert "Number of dis" not in patched
    assert patched.count(GUESS) == 5


def test_fixtures_regenerate_idempotently():
    for code in (AI_TEST_BATCH, INVOICE_SERVICE):
        once = _generate(code)
        assert _generate(once) == once


def test_async_function_raise_condition_and_nested_def_isolation():
    """async def goes through the same path; a raise inside a nested def
    belongs to the nested function, not the outer one."""
    patched = _generate("""async def fetch(url):
    def check(code):
        if code >= 500:
            raise RuntimeError(code)
    if not url:
        raise ValueError("empty url")
    return check
""")
    outer = patched.split("async def fetch", 1)[1].split('"""', 2)[1]
    assert "ValueError: If `not url`." in outer
    assert "RuntimeError" not in outer
    inner = patched.split("def check", 1)[1].split('"""', 2)[1]
    assert "RuntimeError: If `code >= 500`." in inner
