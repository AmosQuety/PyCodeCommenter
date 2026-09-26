"""AI drafting for class docstrings: the summary and every `Attributes:`
entry that would otherwise be a TODO or a type-only filler. Same rules as
functions: author text and facts are never replaced, every drafted line is
labelled, and a declined value leaves its gap as it was."""

import logging

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.description_provider import (
    ClassDraft,
    DescriptionProvider,
    DocstringDraft,
    DraftingStopped,
)

logging.disable(logging.CRITICAL)

MARKER = "(AI-drafted, unreviewed)"
GUESS = "TODO(pycodecommenter)"

SERVICE = """class ProductService(Base):
    LIMIT = 10

    def __init__(self, products, categories: list, customer_id: str):
        self._products = products
        self._categories = categories
        self.customer_id = customer_id
        self.total = 0.0

    def create(self, name):
        return self._products.add(name)
"""


class ClassProvider(DescriptionProvider):
    """Records class requests; answers from ``draft``."""

    def __init__(self, draft=None, error=None):
        self.draft = draft or ClassDraft()
        self.error = error
        self.requests = []

    def draft_class_docstring(self, context, known, slots):
        self.requests.append((context, known, slots))
        if self.error is not None:
            raise self.error
        return self.draft

    def draft_docstring(self, context, known, slots):
        return DocstringDraft()


def generate(code, provider):
    return (
        PyCodeCommenter(description_provider=provider)
        .from_string(code)
        .get_patched_code()
    )


FULL = ClassDraft(
    summary="Manage products and their categories.",
    attributes={
        "_products": "Storage the products are read from and saved to.",
        "_categories": "The categories products can belong to.",
        "total": "Running total of the amounts handled.",
    },
)


# ---------------------------------------------------------------------------
# What is asked for
# ---------------------------------------------------------------------------


def test_summary_and_every_gap_attribute_are_requested():
    provider = ClassProvider()
    generate(SERVICE, provider)

    [(context, known, slots)] = provider.requests
    assert context.name == "ProductService"
    assert context.bases == ["Base"]
    assert slots.summary is True  # "ProductService class." says nothing
    # customer_id has a real name-based description, so it is not a gap.
    assert set(slots.attributes) == {"_products", "_categories", "total"}
    assert known == {"customer_id": "Unique identifier for the customer."}


def test_context_carries_attribute_types_and_a_source_outline():
    provider = ClassProvider()
    generate(SERVICE, provider)

    [(context, _, _)] = provider.requests
    types = {a.name: a.type_hint for a in context.attributes}
    assert types["_categories"] == "list"
    assert types["total"] == "float"
    assert "self._products = products" in context.source  # __init__ in full
    assert "def create(self, name)" in context.source  # other methods: signature
    assert "self._products.add(name)" not in context.source  # ...not their bodies
    assert "LIMIT = 10" in context.source


def test_author_written_class_is_never_asked_about():
    code = '''class Box:
    """A box.

    Attributes:
        size (int): How big the box is.
    """

    def __init__(self, size: int):
        self.size = size
'''
    provider = ClassProvider()
    generate(code, provider)

    assert provider.requests == []


def test_only_the_missing_parts_of_a_partly_written_class_are_requested():
    code = '''class Box:
    """A box for things."""

    def __init__(self, size, colour):
        self.size = size
        self.colour = colour
'''
    provider = ClassProvider()
    generate(code, provider)

    [(_, _, slots)] = provider.requests
    assert slots.summary is False  # the author wrote one
    assert set(slots.attributes) == {"size", "colour"}


def test_a_class_with_nothing_to_draft_makes_no_request():
    provider = ClassProvider()

    generate("class Empty:\n    pass\n", provider)

    assert provider.requests == [] or provider.requests[0][2].attributes == ()


# ---------------------------------------------------------------------------
# What is written
# ---------------------------------------------------------------------------


def test_drafted_class_lines_are_labelled_and_replace_the_todos():
    patched = generate(SERVICE, ClassProvider(FULL))

    assert f"Manage products and their categories. {MARKER}" in patched
    assert (
        f"_products (Any): Storage the products are read from and saved to. {MARKER}"
        in patched
    )
    assert f"total (float): Running total of the amounts handled. {MARKER}" in patched
    assert GUESS not in patched.split("def __init__")[0]
    assert "ProductService class." not in patched


def test_facts_and_author_text_are_not_replaced_by_drafts():
    draft = ClassDraft(
        summary="Ignored when the author wrote one.",
        attributes={"customer_id": "Overwrite attempt."},
    )
    patched = generate(SERVICE, ClassProvider(draft))

    assert "Overwrite attempt." not in patched
    assert "customer_id (str): Unique identifier for the customer." in patched


def test_a_declined_value_leaves_the_gap_as_it_was():
    draft = ClassDraft(summary="null", attributes={"_products": "TODO later"})
    patched = generate(SERVICE, ClassProvider(draft))

    assert MARKER not in patched.split("def __init__")[0]
    assert "ProductService class." in patched
    assert f"_products (Any): {GUESS}" in patched


def test_a_partial_answer_fills_only_what_it_covers():
    draft = ClassDraft(attributes={"total": "Running total."})
    patched = generate(SERVICE, ClassProvider(draft))

    assert f"total (float): Running total. {MARKER}" in patched
    assert f"_products (Any): {GUESS}" in patched  # not covered by the answer


def test_regenerating_finished_output_is_stable_and_asks_nothing_more():
    once = generate(SERVICE, ClassProvider(FULL))
    provider = ClassProvider(FULL)

    twice = generate(once, provider)

    assert twice == once
    assert provider.requests == []


def test_earlier_deterministic_filler_becomes_a_gap_a_later_ai_run_can_fill():
    plain = PyCodeCommenter().from_string(SERVICE).get_patched_code()
    provider = ClassProvider(FULL)

    patched = generate(plain, provider)

    [(_, _, slots)] = provider.requests
    assert set(slots.attributes) == {"_products", "_categories", "total"}
    assert f"total (float): Running total of the amounts handled. {MARKER}" in patched


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_a_provider_without_class_support_leaves_todos_and_does_not_fail():
    class FunctionsOnly(DescriptionProvider):
        def draft_docstring(self, context, known, slots):
            return DocstringDraft()

    patched = generate(SERVICE, FunctionsOnly())

    assert f"_products (Any): {GUESS}" in patched


def test_a_failing_provider_leaves_the_class_as_the_deterministic_output():
    patched = generate(SERVICE, ClassProvider(error=RuntimeError("boom")))

    assert patched == PyCodeCommenter().from_string(SERVICE).get_patched_code()


def test_drafting_stopped_ends_drafting_for_the_file():
    code = (
        SERVICE + "\n\nclass Other:\n    def __init__(self, x):\n        self.x = x\n"
    )
    provider = ClassProvider(error=DraftingStopped("limit", "Daily limit reached."))
    commenter = PyCodeCommenter(description_provider=provider)

    commenter.from_string(code).get_patched_code()

    assert commenter.drafting_stopped is not None
    assert len(provider.requests) == 1  # the second class was not attempted


def test_numpy_style_class_is_filled_in_its_own_style():
    code = '''class Box:
    """Box class.

    Attributes
    ----------
    size : int
        int value.
    """

    def __init__(self, size: int):
        self.size = size
'''
    draft = ClassDraft(
        summary="A box that holds things.", attributes={"size": "How big the box is."}
    )
    patched = generate(code, ClassProvider(draft))

    assert "Attributes\n    ----------" in patched
    assert f"How big the box is. {MARKER}" in patched


# ---------------------------------------------------------------------------
# The end-of-run summary
# ---------------------------------------------------------------------------


def test_summary_counts_class_ai_lines_and_the_gaps_still_left():
    commenter = PyCodeCommenter(description_provider=ClassProvider(FULL))
    commenter.from_string(SERVICE).get_patched_code()

    # summary + three attributes drafted; no class gap left
    assert commenter.report.ai_lines >= 4
    class_todos = commenter.report.todos
    plain = PyCodeCommenter()
    plain.from_string(SERVICE).get_patched_code()
    assert class_todos < plain.report.todos


def test_summary_counts_gaps_left_by_a_provider_that_declines():
    commenter = PyCodeCommenter(description_provider=ClassProvider())
    commenter.from_string(SERVICE).get_patched_code()
    plain = PyCodeCommenter()
    plain.from_string(SERVICE).get_patched_code()

    assert commenter.report.todos == plain.report.todos
    assert commenter.report.ai_lines == 0
