"""Regressions found while preparing v2.6.0: text the author wrote, or the
tool itself wrote on an earlier run, must come back unchanged -- or, if it
is the tool's own placeholder or filler, be recognised as such so it can be
improved (including by --ai-draft).
"""

import ast
import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.description_provider import DescriptionProvider, DocstringDraft

logging.disable(logging.CRITICAL)

GUESS = "TODO(pycodecommenter)"


def generate(code, provider=None):
    return (
        PyCodeCommenter(description_provider=provider)
        .from_string(code)
        .get_patched_code()
    )


class Recorder(DescriptionProvider):
    def __init__(self, draft=None):
        self.requests = []
        self.draft = draft or DocstringDraft()

    def draft_docstring(self, context, known, slots):
        self.requests.append(slots)
        return self.draft


# ---------------------------------------------------------------------------
# An author's __init__ summary is theirs
# ---------------------------------------------------------------------------


def test_author_init_summary_is_kept():
    code = '''class Service:
    def __init__(self, repo):
        """Bind the service to an invoice repository."""
        self.repo = repo
'''
    patched = generate(code)

    assert "Bind the service to an invoice repository." in patched
    assert "Initialize the class." not in patched


def test_fresh_init_still_gets_the_fixed_summary():
    patched = generate("class A:\n    def __init__(self, x):\n        self.x = x\n")

    assert '"""Initialize the class.' in patched


# ---------------------------------------------------------------------------
# The default value is stated once
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "signature, line",
    [
        ("def f(retries: int = 3):", "retries (int): int value. (default: 3)"),
        ("def f(flag: bool = True):", "flag (bool): Boolean flag. (default: True)"),
        # Untyped: a default alone says nothing the suffix doesn't.
        ("def f(retries=3):", f"retries (Any): {GUESS}: describe. (default: 3)"),
    ],
)
def test_default_is_not_repeated_in_the_description(signature, line):
    patched = generate(f"{signature}\n    return 1\n")

    assert line in patched
    assert "Default is" not in patched


def test_untyped_default_only_parameter_is_a_gap_not_a_restatement():
    patched = generate("def f(mode=None):\n    return mode\n")

    assert f"mode (Any): {GUESS}: describe. (default: None)" in patched


# ---------------------------------------------------------------------------
# The tool's own earlier output is not mistaken for author text
# ---------------------------------------------------------------------------

EARLIER_RUN = f'''def total(price, rate: float = 0.5):
    """Total.

    Args:
        price (Any): {GUESS}: describe.
        rate (float): float value. (default: 0.5)

    Returns:
        Any: {GUESS}: describe
    """
    return price * rate
'''


def test_ai_draft_fills_placeholders_left_by_an_earlier_run():
    provider = Recorder()
    generate(EARLIER_RUN, provider)

    [slots] = provider.requests
    assert slots.summary is True  # "Total." is the name-derived summary
    assert slots.params == ("price", "rate")  # a TODO and a type-only filler
    assert slots.returns is True


def test_earlier_run_output_regenerates_unchanged_without_ai():
    assert generate(EARLIER_RUN) == EARLIER_RUN


def test_real_author_text_matching_nothing_generated_is_still_author_text():
    code = '''def total(price):
    """Total.

    Args:
        price (Any): Net price in shillings.
    """
    return price
'''
    provider = Recorder()
    generate(code, provider)

    [slots] = provider.requests
    assert slots.params == ()


# ---------------------------------------------------------------------------
# Escape sequences in existing docstrings survive regeneration
# ---------------------------------------------------------------------------


def test_escape_sequences_in_a_docstring_are_kept_as_written():
    code = '''def parse(text):
    """Split on ``\\n`` or ``\\t`` boundaries.

    Args:
        text (str): Input such as ``"a\\tb"``.
    """
    return text.split()
'''
    patched = generate(code)

    # The literal is kept exactly as written. (Comparing interpreted values
    # doesn't work here: a real line break from `\\n` changes how the
    # docstring's indentation is cleaned.)
    assert "Split on ``\\n`` or ``\\t`` boundaries." in patched
    assert 'Input such as ``"a\\tb"``.' in patched


def test_raw_docstring_keeps_its_prefix():
    code = '''def match(pattern):
    r"""Match digits like \\d+ in ``pattern``.

    Args:
        pattern (str): A regex such as ``\\w+``.
    """
    return pattern
'''
    patched = generate(code)

    assert 'r"""Match digits like \\d+' in patched
    # The original meaning (escapes interpreted) is all still there; the
    # generator only adds sections the original lacked.
    assert ast.get_docstring(ast.parse(code).body[0]) in ast.get_docstring(
        ast.parse(patched).body[0]
    )


def test_escape_regeneration_is_idempotent():
    code = 'def f(x):\n    """Tab: \\t, newline: \\n."""\n    return x\n'
    once = generate(code)

    assert generate(once) == once


# ---------------------------------------------------------------------------
# A bare `raise SomeError` names its class too
# ---------------------------------------------------------------------------


def test_bare_raise_of_a_builtin_exception_is_documented():
    patched = generate("def area(self):\n    raise NotImplementedError\n")

    assert "NotImplementedError: Always." in patched


def test_bare_raise_of_an_exception_named_class_is_documented():
    code = (
        "def load(path):\n"
        "    if not path:\n"
        "        raise ConfigError\n"
        "    return path\n"
    )
    assert "ConfigError: If `not path`." in generate(code)


def test_raising_a_variable_is_still_not_guessed():
    code = (
        "def run(job):\n"
        "    try:\n"
        "        job()\n"
        "    except Exception as err:\n"
        "        raise err\n"
    )
    assert "Raises:" not in generate(code)
