"""Configuration loader for PyCodeCommenter.

Provides a :func:`load_config` function that searches for a ``.pycodecommenter.yaml``
file starting from ``start_path`` (or the current working directory) and walks
up the directory hierarchy until the file is found.

If the file is found it is parsed with ``ruamel.yaml`` and the resulting Python
``dict`` is returned.  If the file cannot be parsed a ``ConfigError`` is raised.
If no configuration file is found an empty ``dict`` is returned.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from ruamel.yaml import YAML


class ConfigError(Exception):
    """Raised when the configuration file exists but cannot be parsed.

    The original exception message is included in the error string for easier
    debugging.
    """

    def __init__(self, message: str, original: Exception | None = None):
        full_msg = message
        if original is not None:
            full_msg = f"{message}: {original}"
        super().__init__(full_msg)
        self.original = original


def _find_config_path(start_path: Optional[str] = None) -> Optional[Path]:
    """Search upward from *start_path* for ``.pycodecommenter.yaml``.

    Returns the :class:`~pathlib.Path` to the config file if found, otherwise
    ``None``.
    """
    if start_path is None:
        start_path = os.getcwd()
    current = Path(start_path).resolve()
    while True:
        candidate = current / ".pycodecommenter.yaml"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            # Reached filesystem root
            return None
        current = current.parent


def load_config(start_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration for PyCodeCommenter.

    Parameters
    ----------
    start_path: str | None, optional
        Directory to start the search from.  Defaults to the current working
        directory.

    Returns
    -------
    dict
        Parsed configuration dictionary.  Returns an empty dictionary if no
        ``.pycodecommenter.yaml`` file is discovered.

    Raises
    ------
    ConfigError
        If a config file is discovered but parsing fails.
    """
    config_path = _find_config_path(start_path)
    if config_path is None:
        return {}
    yaml = YAML(typ="safe")
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
        return data
    except Exception as exc:
        raise ConfigError(f"Failed to parse config file {config_path}", exc) from exc
