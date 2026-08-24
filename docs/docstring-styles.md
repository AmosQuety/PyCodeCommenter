# Docstring Styles Guide

PyCodeCommenter generates **Google-style** docstrings and can **parse** Google-style, Sphinx-style, and NumPy-style docstrings when they already exist. This page explains what that means in practice.

---

## Style Support Overview

| Style | Generation | Parsing (input) | Notes |
|-------|-----------|-----------------|-------|
| Google | Yes — always | Yes — full | The only output format |
| Sphinx (`:param:`, `:return:`) | No | Yes — full, including `:type name: TYPE` | Other Sphinx directives (e.g. `:raises ExcType:`) are silently ignored |
| NumPy (dash-underlined `Parameters`/`Returns`/`Raises`) | No | Yes — full (since v2.3.0) | `Raises` has no dedicated field; its body is folded into `description` |

> The README mentions `style: google`, `style: numpy`, and `style: sphinx` as config values, but the `style` key is **not yet wired into the runtime**. Regardless of any config value, the tool always generates Google-style docstrings; the auto-detect logic below governs *parsing* existing docstrings for the merge step, not generation.

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
| `Yields:` | `returns` string (shares the same slot — both describe what comes back out of the function) |
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

The type in parentheses is optional, and a leading `*`/`**` is recognised for `*args`/`**kwargs` entries. Any non-blank continuation line — regardless of indentation depth — is appended to the previous parameter's description. (Prior to a fix in v2.3.0, only continuation lines indented by exactly 8 spaces were recognised; any other indentation, including the 4-space indent this project's own generator uses, silently truncated the description on merge.)

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

The parser (`DocstringParser._parse_sphinx`) is triggered when `:param` or `:return` appears in the docstring body (and no NumPy-style dash-underlined header is present — NumPy detection runs first, see below). It extracts:

| Field | Sphinx syntax | Extracted to |
|-------|--------------|-------------|
| Summary | First line | `summary` |
| Parameters | `:param name: desc` | `params` dict |
| Parameter types | `:type name: TYPE` | `param_types` dict |
| Return | `:return: desc` or `:returns: desc` | `returns` string |

Multi-line parameter descriptions (continuation lines not starting with `:`) are appended to the previous parameter.

**What is not extracted:** `:rtype:`, `:raises ExcType:`, and other Sphinx directives are silently ignored during parsing.

### Partial support note

Sphinx style is supported for **input only**. After `generate --inplace`, the output will be Google style. If you want to preserve Sphinx style in your output, do not use `--inplace` — use `--dry-run` to review first.

---

## NumPy Style

NumPy-style docstrings use section headers underlined with a row of three or more dashes. Support for parsing this style **as input** was added in v2.3.0.

### Example of a NumPy-style input docstring

```python
def send_request(url: str, method: str = "GET") -> dict:
    """Send an HTTP request to the given URL.

    Parameters
    ----------
    url : str
        URL to send the request to.
    method : str, optional
        HTTP method (GET, POST, etc.).

    Returns
    -------
    dict
        Response data as a dictionary.
    """
    ...
```

### What the parser extracts

The parser (`DocstringParser._parse_numpy`) is triggered by the dash-underlined header signature — it's checked *before* Sphinx or Google detection, since only NumPy style can produce it.

| Field | NumPy syntax | Extracted to |
|-------|-------------|-------------|
| Parameters | `name : type` (or `name1, name2 : type` for a shared type), with the description on following indented lines | `params` dict, `param_types` dict |
| Returns | A bare `type` or `name : type` header line, with the description on following indented lines | `returns` string, as `"<header line>: <description>"` |
| Raises | Anything under a `Raises` header | Folded into `description` (there's no dedicated `raises` field, so this avoids silently dropping the text) |

A trailing `, optional` on a parameter's type (NumPy's convention for a parameter with a default) is stripped before storing.

### Partial support note

NumPy style is supported for **input only**, same as Sphinx. After `generate --inplace`, the output is always Google style.

---

## How the Parser Chooses a Style

Style detection is automatic, based on content. NumPy's dash-underlined headers are the most specific signature — Google's `Args:`-on-one-line and Sphinx's `:param:` can't produce it — so it's checked first:

```python
if self._NUMPY_HEADER_RE.search(remaining_content):
    self._parse_numpy(remaining_content)
elif ":param" in remaining_content or ":return" in remaining_content:
    self._parse_sphinx(remaining_content)
else:
    self._parse_google(remaining_content)
```

There is no explicit style declaration needed: a NumPy-style `Parameters`/`Returns`/`Raises` header underlined with three or more dashes is checked first; failing that, `:param`/`:return` anywhere after the first line selects Sphinx parsing; otherwise Google parsing is used.

---

## Related

- **[Python API](python-api.md)** — `DocstringParser` class reference
- **[Validation Checks](validation-checks.md)** — the `format` category checks for Google-style compliance
- **[Configuration](configuration.md)** — the `style` config key (not yet implemented)
