"""AI drafting fills only the gaps, labels every line it writes, and can
never break the file it writes into.

The provider here is a local fake: these tests are about what the generator
asks for and what it does with the answer, not about any real model.
"""

import ast
import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.ai_drafting import clean_slot_text
from PyCodeCommenter.description_provider import (
    DescriptionProvider,
    DocstringDraft,
    DraftingStopped,
)

logging.disable(logging.CRITICAL)

MARKER = "(AI-drafted, unreviewed)"
GUESS = "TODO(pycodecommenter)"


class FakeProvider(DescriptionProvider):
    """Returns a fixed draft and records every request it receives."""

    def __init__(self, draft=None, error=None):
        self.draft = draft or DocstringDraft()
        self.error = error
        self.requests = []

    def draft_docstring(self, context, known, slots):
        self.requests.append((context, known, slots))
        if self.error is not None:
            raise self.error
        return self.draft


def generate(code, provider):
    return (
        PyCodeCommenter(description_provider=provider)
        .from_string(code)
        .get_patched_code()
    )


FRESH = """def total_due(invoice_id: str, discount, repo):
    invoice = repo.get(invoice_id)
    if invoice is None:
        raise KeyError(invoice_id)
    for line in invoice.lines:
        if line.bad:
            raise ValueError(line)
    return invoice.amount - discount
"""


# ---------------------------------------------------------------------------
# What is asked for
# ---------------------------------------------------------------------------


def test_fresh_function_asks_for_every_gap_and_only_the_gaps():
    provider = FakeProvider()
    generate(FRESH, provider)

    [(context, known, slots)] = provider.requests
    assert context.name == "total_due"
    assert slots.summary is True  # "Total due." is derived from the name
    assert slots.description is True
    # invoice_id has a real name-based description, so it's not a gap.
    assert slots.params == ("discount", "repo")
    assert slots.returns is True
    # KeyError's condition is read off the code; ValueError's isn't.
    assert slots.raises == ("ValueError",)
    assert known.params == {"invoice_id": "Unique identifier for the invoice."}
    assert known.raises == {"KeyError": "If `invoice is None`."}


def test_weak_type_only_description_is_a_gap():
    provider = FakeProvider()
    generate("def pay(amount: float):\n    return amount\n", provider)

    [(_, _, slots)] = provider.requests
    assert slots.params == ("amount",)  # "float value." says nothing new


def test_author_text_is_never_asked_for():
    code = '''def pay(amount):
    """Pay an invoice.

    Args:
        amount: Money to pay, in shillings.

    Returns:
        bool: Whether the payment cleared.
    """
    return amount > 0
'''
    provider = FakeProvider()
    generate(code, provider)

    assert provider.requests == []


def test_nothing_to_draft_means_no_request():
    code = '''def ping():
    """Check the service is up."""
'''
    provider = FakeProvider()
    generate(code, provider)

    assert provider.requests == []


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------

FULL_DRAFT = DocstringDraft(
    summary="Compute what the customer owes on an invoice.",
    description="Looks the invoice up in `repo` and subtracts the discount.",
    params={"discount": "Amount taken off the total.", "repo": "Where invoices live."},
    returns="The amount still owed.",
    raises={"ValueError": "If an invoice line is invalid."},
)


def test_every_drafted_line_is_labelled():
    patched = generate(FRESH, FakeProvider(FULL_DRAFT))

    for text in (
        "Compute what the customer owes on an invoice.",
        "Looks the invoice up in `repo` and subtracts the discount.",
        "Amount taken off the total.",
        "Where invoices live.",
        "The amount still owed.",
        "If an invoice line is invalid.",
    ):
        assert f"{text} {MARKER}" in patched
    assert GUESS not in patched


def test_facts_are_not_replaced_by_drafts():
    draft = DocstringDraft(
        params={"invoice_id": "Overwrite attempt."},
        raises={"KeyError": "Overwrite attempt."},
    )
    patched = generate(FRESH, FakeProvider(draft))

    assert "Overwrite attempt." not in patched
    assert "KeyError: If `invoice is None`." in patched


def test_unsafe_draft_text_is_dropped_and_the_file_still_parses():
    draft = DocstringDraft(
        returns='Ends early """ + injected',
        params={"discount": "Escape \\n sequence."},
    )
    patched = generate(FRESH, FakeProvider(draft))

    ast.parse(patched)
    assert "injected" not in patched
    assert "Escape" not in patched
    assert f"Returns:\n        Any: {GUESS}" in patched


def test_regeneration_keeps_drafts_and_asks_for_nothing_more():
    once = generate(FRESH, FakeProvider(FULL_DRAFT))
    provider = FakeProvider(FULL_DRAFT)

    twice = generate(once, provider)

    assert twice == once
    assert provider.requests == []


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_provider_error_leaves_the_gaps_as_todo():
    patched = generate(FRESH, FakeProvider(error=RuntimeError("boom")))

    assert GUESS in patched
    assert MARKER not in patched


def test_drafting_stopped_skips_the_rest_of_the_run():
    code = FRESH + "\n\ndef other(x):\n    return x\n"
    provider = FakeProvider(
        error=DraftingStopped("user_daily_limit_reached", "Used up.")
    )
    commenter = PyCodeCommenter(description_provider=provider).from_string(code)

    commenter.get_patched_code()

    assert len(provider.requests) == 1
    assert commenter.drafting_stopped.reason == "user_daily_limit_reached"


def test_provider_implementing_only_the_original_interface_still_works():
    """Custom providers written against draft_function_description keep
    filling the description paragraph."""

    class DescriptionOnly(DescriptionProvider):
        def draft_function_description(self, context):
            return "Adds two numbers."

    patched = generate("def add(a, b):\n    return a + b\n", DescriptionOnly())

    assert f"Adds two numbers. {MARKER}" in patched


# ---------------------------------------------------------------------------
# The client-side gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ['has """ quotes', "has ''' quotes", "back\\slash", "TODO later", "", 7, None],
)
def test_clean_slot_text_declines_unsafe_or_empty_values(value):
    assert clean_slot_text(value) is None


def test_clean_slot_text_normalises_whitespace_and_period():
    assert clean_slot_text("  Amount\n owed ") == "Amount owed."
