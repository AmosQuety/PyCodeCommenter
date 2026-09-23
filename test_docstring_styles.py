"""Existing NumPy- and Sphinx-style docstrings keep their style: gaps are
filled in that style, and nothing is converted to Google style. New
docstrings are Google style.
"""

import logging

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.description_provider import DescriptionProvider, DocstringDraft
from PyCodeCommenter.docstring_parser import DocstringParser

logging.disable(logging.CRITICAL)

GUESS = "TODO(pycodecommenter)"


def generate(code, provider=None):
    return (
        PyCodeCommenter(description_provider=provider)
        .from_string(code)
        .get_patched_code()
    )


def docstring_of(patched, name):
    return patched.split(f" {name}(", 1)[1].split('"""', 2)[1]


# ---------------------------------------------------------------------------
# Style detection
# ---------------------------------------------------------------------------


def test_parser_reports_the_style():
    assert DocstringParser("Do it.\n\nArgs:\n    x: y.").get_info()["style"] == "google"
    assert DocstringParser("Do it.").get_info()["style"] == "google"
    assert DocstringParser(":param x: y.").get_info()["style"] == "sphinx"
    numpy = "Do it.\n\nParameters\n----------\nx : int\n    Y."
    assert DocstringParser(numpy).get_info()["style"] == "numpy"


# ---------------------------------------------------------------------------
# NumPy
# ---------------------------------------------------------------------------

NUMPY = '''def load(path: str, strict: bool = False) -> dict:
    """Load a config file.

    Parameters
    ----------
    path : str
        Where the file lives.
    """
    if not path:
        raise ValueError(path)
    return {}
'''


def test_numpy_docstring_keeps_its_style_and_gets_its_gaps_filled():
    doc = docstring_of(generate(NUMPY), "load")

    assert "Args:" not in doc and "Returns:" not in doc and "Raises:" not in doc
    assert "    Parameters\n    ----------\n" in doc
    assert "    path : str\n        Where the file lives.\n" in doc
    assert (
        "    strict : bool, optional\n        Boolean flag. (default: False)\n" in doc
    )
    assert f"    Returns\n    -------\n    dict\n        {GUESS}: describe\n" in doc
    assert "    Raises\n    ------\n    ValueError\n        If `not path`.\n" in doc


def test_numpy_regeneration_is_idempotent():
    once = generate(NUMPY)

    assert generate(once) == once


def test_numpy_raises_text_written_by_the_author_is_kept():
    code = '''def load(path):
    """Load.

    Raises
    ------
    ConfigError
        If the file can't be parsed.
    """
    raise ConfigError(path)
'''
    doc = docstring_of(generate(code), "load")

    assert "    ConfigError\n        If the file can't be parsed.\n" in doc
    assert doc.count("ConfigError") == 1


def test_numpy_generator_gets_a_yields_section():
    code = '''def items(xs):
    """Iterate.

    Parameters
    ----------
    xs : list
        Things.
    """
    for x in xs:
        yield x
'''
    doc = docstring_of(generate(code), "items")

    assert "    Yields\n    ------\n" in doc


def test_numpy_class_attributes_keep_the_style():
    code = '''class Repo:
    """Stores invoices.

    Attributes
    ----------
    store : dict
        Invoices by id.
    """

    def __init__(self, store: dict, limit: int):
        self.store = store
        self.limit = limit
'''
    patched = generate(code)
    doc = patched.split("class Repo:", 1)[1].split('"""', 2)[1]

    assert "Attributes:" not in doc
    assert "    Attributes\n    ----------\n" in doc
    assert "    store : dict\n        Invoices by id.\n" in doc
    assert "    limit : int\n        int value.\n" in doc
    assert generate(patched) == patched


def test_ai_drafts_in_a_numpy_docstring_are_labelled():
    class Drafts(DescriptionProvider):
        def draft_docstring(self, context, known, slots):
            return DocstringDraft(returns="The parsed settings.")

    doc = docstring_of(generate(NUMPY, Drafts()), "load")

    assert "    dict\n        The parsed settings. (AI-drafted, unreviewed)\n" in doc


# ---------------------------------------------------------------------------
# Sphinx
# ---------------------------------------------------------------------------

SPHINX = '''def load(path: str, strict: bool = False) -> dict:
    """Load a config file.

    :param path: Where the file lives.
    """
    if not path:
        raise ValueError(path)
    return {}
'''


def test_sphinx_docstring_keeps_its_style_and_gets_its_gaps_filled():
    doc = docstring_of(generate(SPHINX), "load")

    assert "Args:" not in doc and "Returns:" not in doc
    assert "    :param path: Where the file lives.\n    :type path: str\n" in doc
    assert (
        "    :param strict: Boolean flag. (default: False)\n    :type strict: bool\n"
        in doc
    )
    assert f"    :returns: {GUESS}: describe\n    :rtype: dict\n" in doc
    assert "    :raises ValueError: If `not path`.\n" in doc


def test_sphinx_regeneration_is_idempotent():
    once = generate(SPHINX)

    assert generate(once) == once


def test_sphinx_raises_and_yields_written_by_the_author_are_kept():
    code = '''def items(xs):
    """Iterate.

    :param xs: Things.
    :yields: Each thing in turn.
    :raises KeyError: If a thing is missing.
    """
    for x in xs:
        yield x
    raise KeyError()
'''
    doc = docstring_of(generate(code), "items")

    assert ":yields: Each thing in turn." in doc
    assert ":raises KeyError: If a thing is missing." in doc


def test_sphinx_class_attributes_use_ivar():
    code = '''class Repo:
    """Stores invoices.

    :ivar store: Invoices by id.
    """

    def __init__(self, store: dict):
        self.store = store
'''
    patched = generate(code)
    doc = patched.split("class Repo:", 1)[1].split('"""', 2)[1]

    assert "    :ivar store: Invoices by id.\n    :vartype store: dict\n" in doc
    assert generate(patched) == patched


# ---------------------------------------------------------------------------
# New docstrings
# ---------------------------------------------------------------------------


def test_new_docstrings_are_google_style():
    doc = docstring_of(generate("def f(x: int) -> int:\n    return x\n"), "f")

    assert "Args:\n" in doc and "Returns:\n" in doc
