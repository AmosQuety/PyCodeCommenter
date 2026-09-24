"""Regeneration must never overwrite documentation an author already wrote.

Every section the generator emits either carries the author's existing text
forward or fills a slot that was empty. Before these tests, an author's
Raises: and Attributes: descriptions were replaced with guess markers on
every run, and a hand-written Methods: section was deleted outright -- so
running the tool on a fully documented file made it *less* documented.
"""

import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.docstring_parser import DocstringParser

logging.disable(logging.CRITICAL)

GUESS = "TODO(pycodecommenter)"


@pytest.fixture
def commenter():
    return PyCodeCommenter()


def _docstring_of(patched: str, marker: str) -> str:
    """The docstring text of the first definition whose header contains
    *marker*."""
    after_def = patched.split(marker, 1)[1]
    return after_def.split('"""', 2)[1]


# ---------------------------------------------------------------------------
# Parser: Raises / Attributes / Methods are now parsed, not discarded
# ---------------------------------------------------------------------------


def test_parser_reads_google_raises_entries():
    doc = """Parse a number.

Raises:
    ValueError: If the text is not a number.
    exceptions.ConfigError: If the config
        cannot be read.
"""
    raises = DocstringParser(doc).get_info()["raises"]
    assert raises["ValueError"] == "If the text is not a number."
    assert raises["exceptions.ConfigError"] == "If the config cannot be read."


def test_parser_reads_sphinx_raises_entries():
    doc = """Parse a number.

:param text: Raw text.
:raises ValueError: If the text is not a number.
"""
    assert DocstringParser(doc).get_info()["raises"] == {
        "ValueError": "If the text is not a number."
    }


def test_parser_reads_numpy_raises_entries():
    doc = """Load config.

Raises
------
ConfigError
    If a config file is discovered but parsing fails.
"""
    assert DocstringParser(doc).get_info()["raises"] == {
        "ConfigError": "If a config file is discovered but parsing fails."
    }


def test_parser_reads_google_attributes_with_and_without_types():
    doc = """A customer invoice.

Attributes:
    repo: Storage backend used to load invoices.
    tax_rate (float): VAT rate applied
        to the subtotal.
"""
    info = DocstringParser(doc).get_info()
    assert info["attributes"] == {
        "repo": "Storage backend used to load invoices.",
        "tax_rate": "VAT rate applied to the subtotal.",
    }
    assert info["attribute_types"] == {"tax_rate": "float"}


def test_parser_keeps_methods_section_body_verbatim():
    doc = """A customer invoice.

Methods:
    total(): Amount due including VAT.
"""
    assert DocstringParser(doc).get_info()["methods"] == (
        "    total(): Amount due including VAT."
    )


# ---------------------------------------------------------------------------
# Raises: author text wins; stale generated markers do not
# ---------------------------------------------------------------------------


def test_author_raises_description_survives_regeneration(commenter):
    code = '''def parse(value: str) -> int:
    """Parse a positive integer.

    Args:
        value (str): Raw text from the form.

    Returns:
        int: The parsed number.

    Raises:
        ValueError: If the text is not a positive integer.
    """
    n = int(value)
    if n <= 0:
        raise ValueError(value)
    return n
'''
    patched = commenter.from_string(code).get_patched_code()
    assert "ValueError: If the text is not a positive integer." in patched
    assert GUESS not in patched


def test_author_raises_matched_by_short_name(commenter):
    """An author may document `errors.ConfigError` while the code raises it
    via a bare name (or vice versa) -- the same exception, not two."""
    code = '''def load():
    """Load.

    Raises:
        errors.ConfigError: If the file is unreadable.
    """
    raise ConfigError("bad")
'''
    docstring = _docstring_of(
        commenter.from_string(code).get_patched_code(), "def load"
    )
    assert docstring.count("ConfigError") == 1
    assert "If the file is unreadable." in docstring


def test_author_documented_propagated_exception_is_kept(commenter):
    """`int(value)` raising ValueError is a real, documented behaviour even
    though no `raise` statement for it appears in the function body."""
    code = '''def parse(value: str) -> int:
    """Parse.

    Raises:
        ValueError: If value is not numeric.
    """
    return int(value)
'''
    patched = commenter.from_string(code).get_patched_code()
    assert "ValueError: If value is not numeric." in patched


def test_stale_generated_raises_marker_is_not_kept_for_unraised_exception(
    commenter,
):
    """A marker line the tool itself wrote on an earlier run is not author
    text -- once the code stops raising that exception, it goes."""
    code = f'''def parse(value):
    """Parse.

    Raises:
        KeyError: {GUESS}: describe when this is raised.
    """
    return value
'''
    patched = commenter.from_string(code).get_patched_code()
    assert "KeyError" not in _docstring_of(patched, "def parse")


def test_stale_generated_raises_marker_is_replaced_by_derived_fact(commenter):
    code = f'''def check(x):
    """Check.

    Raises:
        ValueError: {GUESS}: describe when this is raised.
    """
    if x < 0:
        raise ValueError("negative")
'''
    patched = commenter.from_string(code).get_patched_code()
    raises = patched.split("Raises:\n", 1)[1].split('"""', 1)[0]
    assert raises.strip() == "ValueError: If `x < 0`."


# ---------------------------------------------------------------------------
# Attributes: author text wins
# ---------------------------------------------------------------------------

_DOCUMENTED_CLASS = '''class Invoice:
    """A customer invoice.

    Attributes:
        repo: Storage backend used to load invoices.
        tax_rate (float): VAT rate applied to the subtotal.
        CURRENCY (str): ISO currency code for all amounts.

    Methods:
        total(): Amount due including VAT.
    """

    CURRENCY = "UGX"

    def __init__(self, repo, tax_rate: float = 0.18):
        self.repo = repo
        self.tax_rate = tax_rate

    def total(self):
        return 0
'''


def test_author_attribute_descriptions_survive_regeneration(commenter):
    docstring = _docstring_of(
        commenter.from_string(_DOCUMENTED_CLASS).get_patched_code(), "class Invoice"
    )
    assert "repo (Any): Storage backend used to load invoices." in docstring
    assert "tax_rate (float): VAT rate applied to the subtotal." in docstring
    assert GUESS not in docstring


def test_author_documented_attribute_not_detected_in_code_is_kept(commenter):
    """Class-level constants, properties and the like are legitimately
    documented under Attributes: even where attribute detection doesn't
    find them."""
    docstring = _docstring_of(
        commenter.from_string(_DOCUMENTED_CLASS).get_patched_code(), "class Invoice"
    )
    assert "CURRENCY (str): ISO currency code for all amounts." in docstring


def test_author_methods_section_is_kept(commenter):
    docstring = _docstring_of(
        commenter.from_string(_DOCUMENTED_CLASS).get_patched_code(), "class Invoice"
    )
    assert "Methods:\n        total(): Amount due including VAT." in docstring


def test_class_docstring_regeneration_is_idempotent(commenter):
    once = commenter.from_string(_DOCUMENTED_CLASS).get_patched_code()
    twice = PyCodeCommenter().from_string(once).get_patched_code()
    assert once == twice


# ---------------------------------------------------------------------------
# Methods: never generated; leftover generated entries are cleaned up
# ---------------------------------------------------------------------------


def test_methods_section_is_not_generated(commenter):
    """Methods: is not a standard Google-style section (the tool's own
    validator reports it as non-standard), every public method gets its own
    docstring, and nothing the AST knows about a method fits in one line
    without guessing."""
    code = """class Widget:
    def render(self):
        return 1

    def close(self):
        pass
"""
    patched = commenter.from_string(code).get_patched_code()
    assert "Methods:" not in patched


def test_previously_generated_methods_entries_are_removed(commenter):
    code = f'''class Widget:
    """Widget class.

    Methods:
        render(): {GUESS}: describe
        close(): {GUESS}: describe
    """

    def render(self):
        return 1

    def close(self):
        pass
'''
    docstring = _docstring_of(
        commenter.from_string(code).get_patched_code(), "class Widget"
    )
    assert "Methods:" not in docstring
    assert GUESS not in docstring


def test_mixed_methods_section_keeps_only_author_entries(commenter):
    code = f'''class Widget:
    """Widget class.

    Methods:
        render(): Draws the widget
            onto the current canvas.
        close(): {GUESS}: describe
    """

    def render(self):
        return 1

    def close(self):
        pass
'''
    docstring = _docstring_of(
        commenter.from_string(code).get_patched_code(), "class Widget"
    )
    assert (
        "Methods:\n        render(): Draws the widget\n"
        "            onto the current canvas.\n"
    ) in docstring
    assert "close()" not in docstring
