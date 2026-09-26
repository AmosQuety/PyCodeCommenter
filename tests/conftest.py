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
