"""Source that looks like it holds a secret is never sent to an AI service.
Fake secrets are assembled at run time so this file itself contains nothing
a secret scanner would flag."""

import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.description_provider import (
    ClassDraft,
    DescriptionProvider,
    DocstringDraft,
)
from PyCodeCommenter.draft_limits import DraftBudget
from PyCodeCommenter.secret_scan import looks_like_secret

logging.disable(logging.CRITICAL)

RANDOM = "Q7xZ2mK9vB4nL1pR8sT3wY6"  # 23 characters, no meaning

SECRETS = {
    "private key": "-----BEGIN " + "RSA PRIVATE KEY" + "-----\nMIIE...",
    "aws key": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "google key": "AI" + "za" + "SyA-" + RANDOM + "abcdefghijkl",
    "openai style key": "sk" + "-" + RANDOM + "abcdef",
    "anthropic style key": "sk" + "-ant-" + RANDOM + "abcdef",
    "github token": "gh" + "p_" + RANDOM + "abcdefghijklmnopqrstu",
    "slack token": "xo" + "xb-" + "1234567890-" + RANDOM,
    "jwt": "ey"
    + "JhbGciOiJIUzI1NiJ9"
    + "."
    + "ey"
    + "JzdWIiOiIxMjM0NTY3ODkw"
    + "."
    + RANDOM,
}


@pytest.mark.parametrize("kind", SECRETS)
def test_well_known_credential_shapes_are_recognised(kind):
    assert looks_like_secret(f"def f():\n    x = '{SECRETS[kind]}'\n")


@pytest.mark.parametrize(
    "line",
    [
        'password = "' + RANDOM + '"',
        "DB_PASSWORD: str = '" + RANDOM + "'",
        'api_key = "' + RANDOM + '"',
        "self.client_secret = '" + RANDOM + "'",
        'headers = {"token": "' + RANDOM + '"}',
        "url = 'postgres://admin:" + RANDOM + "@db.internal/app'",
    ],
)
def test_secret_named_variables_with_a_literal_value_are_recognised(line):
    assert looks_like_secret(f"def f():\n    {line}\n")


@pytest.mark.parametrize(
    "line",
    [
        "token_count = 5",
        "password = getpass.getpass()",
        'api_key = os.environ["API_KEY"]',
        "secret = None",
        'password = ""',
        'token = "abc"',
        "if token == expected_token:",
        'label = "Enter your password below"',
        "url = 'https://example.com/path'",
        "return sha256(data).hexdigest()",
    ],
)
def test_ordinary_code_is_not_flagged(line):
    assert not looks_like_secret(f"def f():\n    {line}\n")


def test_a_comment_holding_a_secret_is_flagged_too():
    assert looks_like_secret(
        "def f():\n    # temporary key: " + SECRETS["aws key"] + "\n"
    )


# ---------------------------------------------------------------------------
# What generation does about it
# ---------------------------------------------------------------------------


class Recording(DescriptionProvider):
    def __init__(self):
        self.sources = []

    def draft_docstring(self, context, known, slots):
        self.sources.append(context.source)
        return DocstringDraft()

    def draft_class_docstring(self, context, known, slots):
        self.sources.append(context.source)
        return ClassDraft()


LEAKY = (
    "def connect(host):\n    key = '"
    + SECRETS["openai style key"]
    + "'\n    return host, key\n"
    "\n\ndef safe(x):\n    return x\n"
)


def run(code, budget=None):
    provider = Recording()
    commenter = PyCodeCommenter(description_provider=provider, budget=budget)
    commenter.from_string(code).get_patched_code()
    return provider, commenter.report


def test_a_function_that_looks_like_it_holds_a_secret_is_not_sent():
    provider, report = run(LEAKY)

    assert len(provider.sources) == 1
    assert "def safe" in provider.sources[0]
    assert all(SECRETS["openai style key"] not in s for s in provider.sources)
    assert report.ai_withheld == 1


def test_a_class_whose_outline_holds_a_secret_is_not_sent():
    code = (
        "class Client:\n    TOKEN = '" + SECRETS["github token"] + "'\n\n"
        "    def __init__(self, url):\n        self.url = url\n"
    )

    provider, report = run(code)

    assert all(SECRETS["github token"] not in s for s in provider.sources)
    assert report.ai_withheld >= 1


def test_a_withheld_function_does_not_use_up_the_draft_budget():
    budget = DraftBudget(limit=1)

    provider, _ = run(LEAKY, budget)

    assert len(provider.sources) == 1  # `safe` still got its request
    assert budget.spent is False


def test_the_summary_says_so_without_showing_the_secret():
    _, report = run(LEAKY)
    text = "\n".join(report.summary_lines(preview=False, ai_used=True))

    assert "1 function or class not sent to the AI" in text
    assert "secret" in text
    assert SECRETS["openai style key"] not in text


def test_the_withheld_function_still_gets_its_deterministic_docstring():
    commenter = PyCodeCommenter(description_provider=Recording())
    patched = commenter.from_string(LEAKY).get_patched_code()

    assert "connect" in patched and "TODO(pycodecommenter)" in patched


def test_without_a_provider_nothing_is_withheld_or_counted():
    commenter = PyCodeCommenter()
    commenter.from_string(LEAKY).get_patched_code()

    assert commenter.report.ai_withheld == 0
