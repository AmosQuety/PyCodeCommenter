# Docstring Styles Guide

PyCodeCommenter generates **Google-style** docstrings and can **parse** both Google-style and Sphinx-style docstrings when they already exist. This page explains what that means in practice.

---

## Style Support Overview

| Style | Generation | Parsing (input) | Notes |
|-------|-----------|-----------------|-------|
| Google | Yes — always | Yes — full | The only output format |
| Sphinx (`:param:`, `:return:`) | No | Yes — partial | Summary, params, and return are extracted; other Sphinx directives are ignored |
| NumPy | No | No | Not implemented; README roadmap item |

> The README mentions `style: google`, `style: numpy`, and `style: sphinx` as config values, but the `style` key is **not yet wired into the runtime**. Regardless of any config value, the tool always generates Google-style docstrings and uses the auto-detect logic described below.

---

## Google Style

Google-style docstrings use indented sections with keyword headers followed by a colon. This is the only format PyCodeCommenter generates.

### Complete example

```python
def connect_to_database(host: str, port: int, timeout: float = 30.0) -> bool:
    """Connect to the database server.

    Establishes a connection to the specified host and port, using the
    provided timeout for both the connection and query phases.

    Args:
        host (str): Database host address.
        port (int): Port number for the database connection.
        timeout (float): Timeout in seconds. Default is 30.0.

    Returns:
        bool: True if the connection was established successfully.

    Raises:
        ConnectionError: If the server cannot be reached.
        ValueError: If port is not in the valid range 1–65535.

    Example:
        >>> ok = connect_to_database("localhost", 5432)
        >>> print(ok)
        True
    """
    ...
```

### Recognised section headers

The parser (`DocstringParser._parse_google`) splits on these headers:

| Header | Parsed into |
|--------|-------------|
| `Args:` | `params` dict |
| `Returns:` | `returns` string |
| `Attributes:` | `description` block (not separately indexed) |
| `Methods:` | `description` block (not separately indexed) |

The **validator** additionally recognises these as valid headers (they do not trigger the "non-standard header" warning):

`Args:`, `Returns:`, `Raises:`, `Yields:`, `Attributes:`, `Example:`, `Examples:`, `Note:`, `Notes:`

### Parameter format

The parser matches lines of the form:

```
    name (type): description
    name: description
```

The type in parentheses is optional. Continuation lines (indented by 8 or more spaces) are appended to the previous parameter's description.

### How to select Google style

Google style is always used. There is no flag or config key needed.

---

## Sphinx Style

Sphinx-style docstrings use reStructuredText field lists. PyCodeCommenter can **read** these and extract the summary, parameters, and return description during the merge step. This means that if your codebase already uses Sphinx-style docstrings, running `generate --inplace` will preserve the existing text and reformat the output as Google style.

### Example of a Sphinx-style input docstring

```python
def send_request(url: str, method: str = "GET") -> dict:
    """Send an HTTP request to the given URL.

    :param url: URL to send the request to.
    :param method: HTTP method (GET, POST, etc.).
    :return: Response data as a dictionary.
    """
    ...
```

### What the parser extracts

The parser (`DocstringParser._parse_sphinx`) is triggered when `:param` or `:return` appears in the docstring body. It extracts:

| Field | Sphinx syntax | Extracted to |
|-------|--------------|-------------|
| Summary | First line | `summary` |
| Parameters | `:param name: desc` | `params` dict |
| Return | `:return: desc` or `:returns: desc` | `returns` string |

Multi-line parameter descriptions (continuation lines not starting with `:`) are appended to the previous parameter.

**What is not extracted:** `:type name:`, `:rtype:`, `:raises ExcType:`, and other Sphinx directives are silently ignored during parsing.

### Partial support note

Sphinx style is supported for **input only**. After `generate --inplace`, the output will be Google style. If you want to preserve Sphinx style in your output, do not use `--inplace` — use `--dry-run` to review first.

---

## NumPy Style

NumPy style is **not implemented**. The parser does not detect or handle NumPy-style section headers (lines followed by a row of dashes). NumPy-style docstrings will be treated as a single `description` block with no structured parameter extraction.

If you need NumPy support, this is on the project roadmap.

---

## How the Parser Chooses a Style

Style detection is automatic, based on content:

```python
if ":param" in remaining_content or ":return" in remaining_content:
    self._parse_sphinx(remaining_content)
else:
    self._parse_google(remaining_content)
```

There is no explicit style declaration needed — if `:param` or `:return` appears anywhere after the first line, Sphinx parsing is used; otherwise Google parsing is used.

---

## Related

- **[Python API](python-api.md)** — `DocstringParser` class reference
- **[Validation Checks](validation-checks.md)** — the `format` category checks for Google-style compliance
- **[Configuration](configuration.md)** — the `style` config key (not yet implemented)
