"""Tests for the one-time, versioned hosted-AI consent flow. Reads/writes a
real (temporary) file rather than mocking the filesystem, since the whole
point of this module is the on-disk read/write/version-mismatch behavior --
mocking it away would test nothing.
"""

import json

import pytest

import PyCodeCommenter.consent as consent


@pytest.fixture(autouse=True)
def _isolated_consent_file(tmp_path, monkeypatch):
    """Every test gets its own ~/.pycodecommenter/consent.json equivalent,
    never the real user's file."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(consent.Path, "home", staticmethod(lambda: fake_home))
    yield fake_home


def test_no_consent_file_means_not_consented():
    assert consent.has_given_consent() is False


def test_record_then_has_given_consent_round_trips():
    consent.record_consent()

    assert consent.has_given_consent() is True


def test_consent_file_persists_the_current_version():
    consent.record_consent()

    path = consent._consent_file_path()
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == {"hosted_ai_consent_version": consent.CONSENT_NOTICE_VERSION}


def test_stale_version_is_not_treated_as_consent(monkeypatch):
    consent.record_consent()
    monkeypatch.setattr(
        consent, "CONSENT_NOTICE_VERSION", consent.CONSENT_NOTICE_VERSION + 1
    )

    assert consent.has_given_consent() is False


def test_corrupt_consent_file_is_treated_as_no_consent():
    path = consent._consent_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{")

    assert consent.has_given_consent() is False


def test_ensure_consent_assume_yes_records_without_prompting(monkeypatch):
    # If input() were called, this would raise -- proving assume_yes skips it.
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError))

    result = consent.ensure_consent(assume_yes=True)

    assert result is True
    assert consent.has_given_consent() is True


def test_ensure_consent_already_consented_skips_prompt_even_without_assume_yes(
    monkeypatch,
):
    consent.record_consent()
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError))

    assert consent.ensure_consent(assume_yes=False) is True


def test_ensure_consent_interactive_yes_records_consent(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda: "y")

    result = consent.ensure_consent(assume_yes=False)

    assert result is True
    assert consent.has_given_consent() is True
    assert "hosted service" in capsys.readouterr().err  # prompts go to stderr


def test_ensure_consent_interactive_no_does_not_record_consent(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: "n")

    result = consent.ensure_consent(assume_yes=False)

    assert result is False
    assert consent.has_given_consent() is False


def test_ensure_consent_empty_answer_declines(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda: "")

    assert consent.ensure_consent(assume_yes=False) is False
