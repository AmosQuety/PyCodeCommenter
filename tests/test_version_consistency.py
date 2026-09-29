"""The version is written in two places; they must never disagree."""

import re
from pathlib import Path

import PyCodeCommenter

ROOT = Path(__file__).resolve().parent.parent


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1]
    return re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE).group(1)


def test_package_version_matches_pyproject():
    assert PyCodeCommenter.__version__ == _project_version()
