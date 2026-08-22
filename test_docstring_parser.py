"""Unit tests for DocstringParser (Phase 6: type preservation and
NumPy-style parsing)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter.docstring_parser import DocstringParser
except ImportError:
    from docstring_parser import DocstringParser


# --- 6a: type capture -------------------------------------------------

def test_parse_google_args_extracts_type():
    doc = """Custom summary.

Args:
    x (int): custom description that should survive.

Returns:
    int: result.
"""
    info = DocstringParser(doc).get_info()
    assert info["params"]["x"] == "custom description that should survive."
    assert info["param_types"]["x"] == "int"


def test_parse_google_args_no_type_present():
    doc = """Summary.

Args:
    x: description without a type.
"""
    info = DocstringParser(doc).get_info()
    assert info["params"]["x"] == "description without a type."
    assert "x" not in info["param_types"]


def test_parse_sphinx_type_directive():
    doc = """Summary.

:param x: the value.
:type x: int
:returns: the result.
"""
    info = DocstringParser(doc).get_info()
    assert info["params"]["x"] == "the value."
    assert info["param_types"]["x"] == "int"


# --- 6b: NumPy detection + parsing -------------------------------------

def test_parse_numpy_params_and_returns():
    # Mirrors config.py's real load_config() docstring shape.
    doc = """Load configuration for PyCodeCommenter.

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
    info = DocstringParser(doc).get_info()
    assert info["params"]["start_path"].startswith("Directory to start the search from.")
    assert info["param_types"]["start_path"] == "str | None"   # ", optional" stripped
    assert info["returns"].startswith("dict:")
    assert "Parsed configuration dictionary." in info["returns"]
    # Raises has no first-class field; folded into description, non-lossy.
    assert "ConfigError" in info["description"]


def test_parse_numpy_multi_name_shared_type():
    doc = """Summary.

Parameters
----------
x, y : int
    Coordinates of the point.
"""
    info = DocstringParser(doc).get_info()
    assert info["params"]["x"] == "Coordinates of the point."
    assert info["params"]["y"] == "Coordinates of the point."
    assert info["param_types"]["x"] == "int"
    assert info["param_types"]["y"] == "int"


def test_parse_numpy_type_strips_trailing_optional_marker():
    doc = """Summary.

Parameters
----------
start_path : str, optional
    Directory to search from.
"""
    assert DocstringParser(doc).get_info()["param_types"]["start_path"] == "str"


def test_parse_google_still_used_when_no_numpy_signature():
    # Regression: a docstring that merely contains the word "Returns" in
    # prose (no dash-underline) must NOT be misdetected as NumPy.
    doc = """Search upward from start_path for the config file.

Returns the path to the config file if found, otherwise None.
"""
    info = DocstringParser(doc).get_info()
    assert info["params"] == {}
    assert "Returns the path" in info["description"]
