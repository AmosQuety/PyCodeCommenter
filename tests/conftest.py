"""Shared pytest configuration."""

import pytest

# Sample source files used as generator input, not test modules.
collect_ignore = ["fixtures"]


@pytest.fixture(autouse=True)
def provider_sdks_are_installed(monkeypatch):
    """Tests use fake provider clients, so they must not depend on which AI
    SDKs happen to be installed on the machine running them. A test about a
    missing SDK overrides this."""
    monkeypatch.setattr("PyCodeCommenter.ai_setup.sdk_installed", lambda name: True)


@pytest.fixture(autouse=True)
def rate_limit_waits_do_not_sleep(monkeypatch):
    """A provider waits out a rate limit before giving up; tests must never
    really sleep. A test about the wait records it by patching `_wait`."""
    monkeypatch.setattr("PyCodeCommenter.direct_providers._wait", lambda seconds: None)
