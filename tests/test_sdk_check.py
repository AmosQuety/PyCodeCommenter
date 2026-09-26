"""The SDK a bring-your-own-key provider needs is checked before the user
is asked for consent or a key, and the failure names the exact command to
run. The tool itself never runs pip."""

import shlex
import sys

import pytest

from PyCodeCommenter import ai_setup, direct_providers
from PyCodeCommenter.ai_setup import AISetupError
from PyCodeCommenter.cli import main
from PyCodeCommenter.description_provider import DraftingStopped

# ---------------------------------------------------------------------------
# Detecting the SDK
# ---------------------------------------------------------------------------


def fake_find_spec(installed):
    def find_spec(name):
        parent = name.split(".")[0]
        if not any(module.split(".")[0] == parent for module in installed):
            raise ModuleNotFoundError(name)
        return object() if name in installed else None

    return find_spec


@pytest.mark.parametrize(
    "provider, module",
    [
        ("gemini", "google.genai"),
        ("openai", "openai"),
        ("anthropic", "anthropic"),
        ("deepseek", "openai"),
        ("openai-compatible", "openai"),
    ],
)
def test_each_provider_is_detected_by_its_own_sdk_module(monkeypatch, provider, module):
    monkeypatch.setattr(
        direct_providers.importlib.util, "find_spec", fake_find_spec({module})
    )

    assert direct_providers.sdk_installed(provider) is True


def test_missing_sdk_is_reported_even_when_the_parent_package_is_missing(monkeypatch):
    # find_spec("google.genai") raises when "google" itself is absent.
    monkeypatch.setattr(
        direct_providers.importlib.util, "find_spec", fake_find_spec(set())
    )

    assert direct_providers.sdk_installed("gemini") is False


def test_a_sibling_package_does_not_count_as_the_gemini_sdk(monkeypatch):
    monkeypatch.setattr(
        direct_providers.importlib.util, "find_spec", fake_find_spec({"google"})
    )

    assert direct_providers.sdk_installed("gemini") is False


def test_install_command_uses_this_python_and_the_providers_extra():
    command = direct_providers.install_command("deepseek")

    assert shlex.split(command) == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "pycodecommenter[openai]",
    ]


# ---------------------------------------------------------------------------
# Failing early
# ---------------------------------------------------------------------------


@pytest.fixture
def no_sdk(monkeypatch):
    monkeypatch.setattr(ai_setup, "sdk_installed", lambda name: False)


@pytest.fixture
def nothing_may_be_asked(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the user was asked before the SDK check")

    monkeypatch.setattr(ai_setup, "ensure_consent", fail)
    monkeypatch.setattr(ai_setup.getpass, "getpass", fail)


def test_missing_sdk_fails_before_consent_and_before_the_key_prompt(
    no_sdk, nothing_may_be_asked, monkeypatch
):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(AISetupError) as raised:
        ai_setup.direct_provider("gemini", None, None)

    message = str(raised.value)
    assert "Gemini" in message
    assert direct_providers.install_command("gemini") in message
    assert "--ai-provider" in message  # says how to pick another one


def test_the_cli_stops_with_the_command_and_asks_nothing(
    no_sdk, nothing_may_be_asked, tmp_path, monkeypatch, capsys
):
    source = tmp_path / "a.py"
    source.write_text("def foo(x):\n    return x\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pycodecommenter",
            "generate",
            str(source),
            "--ai-draft",
            "--ai-provider",
            "gemini",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        main()

    out = capsys.readouterr().out
    assert raised.value.code == 1
    assert 'pycodecommenter[gemini]"' in out or "pycodecommenter[gemini]" in out


def test_an_installed_sdk_goes_on_to_consent_and_key(monkeypatch):
    monkeypatch.setattr(ai_setup, "sdk_installed", lambda name: True)
    asked = []
    monkeypatch.setattr(
        ai_setup, "ensure_consent", lambda **kw: asked.append("consent") or True
    )
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(
        ai_setup,
        "make_provider",
        lambda name, key, model=None, base_url=None: type("P", (), {"model": "m"})(),
    )

    ai_setup.direct_provider("gemini", None, None)

    assert asked == ["consent"]


# ---------------------------------------------------------------------------
# Trying another provider after a failure
# ---------------------------------------------------------------------------


def answers(monkeypatch, replies):
    iterator = iter(replies)
    monkeypatch.setattr(ai_setup, "_ask", lambda prompt: next(iterator))


STOPPED = DraftingStopped("user_daily_limit_reached", "Daily limit reached.")


def test_offer_asks_again_after_a_provider_that_cannot_be_used(monkeypatch, capsys):
    tried = []

    def direct(choice, model, base_url, assume_consent=False):
        tried.append(choice)
        if choice == "gemini":
            raise AISetupError("The Gemini provider needs its SDK.")
        return "the-anthropic-provider"

    monkeypatch.setattr(ai_setup, "direct_provider", direct)
    answers(monkeypatch, ["gemini", "anthropic"])

    result = ai_setup.offer_own_key(STOPPED)

    assert result == "the-anthropic-provider"
    assert tried == ["gemini", "anthropic"]
    assert "Can't continue with Gemini" in capsys.readouterr().err


def test_offer_stops_when_the_user_types_skip_after_a_failure(monkeypatch):
    def direct(choice, model, base_url, assume_consent=False):
        raise AISetupError("The Gemini provider needs its SDK.")

    monkeypatch.setattr(ai_setup, "direct_provider", direct)
    answers(monkeypatch, ["gemini", "skip"])

    assert ai_setup.offer_own_key(STOPPED) is None


def test_offer_with_an_immediate_skip_asks_only_once(monkeypatch):
    asked = []
    monkeypatch.setattr(ai_setup, "_ask", lambda prompt: asked.append(prompt) or "skip")

    assert ai_setup.offer_own_key(STOPPED) is None
    assert len(asked) == 1


def test_offer_does_not_crash_when_input_ends(monkeypatch):
    def end_of_input(prompt):
        raise EOFError

    monkeypatch.setattr(ai_setup, "_ask", end_of_input)

    assert ai_setup.offer_own_key(STOPPED) is None
