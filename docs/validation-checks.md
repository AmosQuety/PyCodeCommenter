# Validation Checks Reference

The validator (`DocstringValidator`) runs six categories of checks whenever `validate_all()` is called. Each check may produce issues at one of three severity levels:

- **ERROR** — a real problem that causes `pycodecommenter validate` to exit with code 1
- **WARNING** — an inconsistency that should be fixed but does not fail the build
- **INFO** — a style or quality hint; never causes a non-zero exit

Below is a summary table followed by a detailed breakdown of every check.

---

## Summary Table

| Check | Severity | Category string |
|-------|----------|-----------------|
| Missing docstring (function) | ERROR | `missing` |
| Missing docstring (class) | ERROR | `missing` |
| Parameter not documented | ERROR | `signature` |
| Parameter documented but not in signature | WARNING | `signature` |
| Parameter order mismatch | INFO | `signature` |
| `self` or `cls` documented in Args | WARNING | `signature` |
| Return type hint but no `Returns:` section | WARNING | `types` |
| Annotated param not in docstring | INFO | `types` |
| Raises statements without `Raises:` section | WARNING | `exceptions` |
| Returns a value but no `Returns:` section | WARNING | `returns` |
| Has `Returns:` section but no return value | INFO | `returns` |
| Empty docstring | ERROR | `format` |
| Missing summary line | ERROR | `format` |
| Non-standard section header | INFO | `format` |
| Placeholder text found | WARNING | `quality` |
| Summary line too short (< 10 chars) | INFO | `quality` |
| Duplicate parameter descriptions | WARNING | `quality` |
| Summary and description are identical | INFO | `quality` |

---

## Missing Docstring (Function)

**Severity:** ERROR
**Category:** `missing`

**What it checks:** Every function (`def` or `async def`) must have a docstring. If the first statement of the function body is not a string literal, this check fires.

**Example violation:**
```python
def process_data(data, timeout=30):
    return data.strip()
```

**Example of passing code:**
```python
def process_data(data, timeout=30):
    """Process the data."""
    return data.strip()
```

**How to fix:** Run `pycodecommenter generate <file> --inplace` to add a starter docstring, then refine it.

---

## Missing Docstring (Class)

**Severity:** ERROR
**Category:** `missing`

**What it checks:** Every class definition must have a docstring.

**Example violation:**
```python
class DataProcessor:
    def __init__(self):
        self.data = []
```

**Example of passing code:**
```python
class DataProcessor:
    """Processes data records.

    DataProcessor class for [describe purpose].
    """
    def __init__(self):
        self.data = []
```

**How to fix:** Add a docstring as the first statement of the class body.

---

## Parameter Not Documented

**Severity:** ERROR
**Category:** `signature`

**What it checks:** Every parameter in the function signature (excluding `self` and `cls`) must appear in the `Args:` section of the docstring.

**Example violation:**
```python
def calculate(price: float, tax: float):
    """Calculate the total.

    Args:
        price (float): The item price.
    """
    return price + tax
```

`tax` is in the signature but missing from `Args:`.

**Example of passing code:**
```python
def calculate(price: float, tax: float):
    """Calculate the total.

    Args:
        price (float): The item price.
        tax (float): The tax rate to apply.
    """
    return price + tax
```

**How to fix:** Add all missing parameters to the `Args:` section.

---

## Parameter Documented but Not in Signature

**Severity:** WARNING
**Category:** `signature`

**What it checks:** Parameters listed in the `Args:` section must actually exist in the function signature. Stale entries from a previous version of the function are caught here.

**Example violation:**
```python
def greet(name: str):
    """Greet a user.

    Args:
        name (str): The user's name.
        title (str): Obsolete parameter removed from signature.
    """
    return f"Hello, {name}"
```

**Example of passing code:**
```python
def greet(name: str):
    """Greet a user.

    Args:
        name (str): The user's name.
    """
    return f"Hello, {name}"
```

**How to fix:** Remove the obsolete entry from `Args:`, or add the parameter back to the function signature.

---

## Parameter Order Mismatch

**Severity:** INFO
**Category:** `signature`

**What it checks:** When all parameters are accounted for (no missing, no extra), the order in `Args:` should match the order in the function signature. This check only fires when the parameter sets are identical.

**Example violation:**
```python
def connect(host: str, port: int):
    """Connect to a server.

    Args:
        port (int): The server port.
        host (str): The server hostname.
    """
```

**Example of passing code:**
```python
def connect(host: str, port: int):
    """Connect to a server.

    Args:
        host (str): The server hostname.
        port (int): The server port.
    """
```

**How to fix:** Reorder the `Args:` entries to match the signature order. The suggestion includes the correct order.

---

## `self` or `cls` Documented in Args

**Severity:** WARNING
**Category:** `signature`

**What it checks:** `self` and `cls` should never appear in the `Args:` section. They are implementation details, not parameters the caller provides.

**Example violation:**
```python
class MyClass:
    def update(self, value):
        """Update the value.

        Args:
            self: The instance.
            value (int): The new value.
        """
        self.value = value
```

**How to fix:** Remove `self` (or `cls`) from the `Args:` section.

---

## Return Type Hint Without `Returns:` Section

**Severity:** WARNING
**Category:** `types`

**What it checks:** If the function has a return type annotation (e.g., `-> str`) but the docstring has no `Returns:` section, this is flagged.

**Example violation:**
```python
def get_name() -> str:
    """Get the name.

    Args:
        None.
    """
    return self.name
```

**How to fix:** Add a `Returns:` section.

---

## Annotated Parameter Not Documented

**Severity:** INFO
**Category:** `types`

**What it checks:** A parameter that has a type annotation but is absent from the `Args:` section is a lighter-weight hint (INFO, not ERROR) caught here. The ERROR-level `signature` check covers the same case — this check fires only when the param has an annotation.

**How to fix:** Document the parameter in the `Args:` section.

---

## Raises Without `Raises:` Section

**Severity:** WARNING
**Category:** `exceptions`

**What it checks:** If the function body contains any `raise` statements and the docstring has no `Raises:` section, this fires. The validator looks for `Raises:` or `Raises\n` or `:raises` in the docstring text.

**Example violation:**
```python
def divide(a, b):
    """Divide two numbers.

    Args:
        a (float): Numerator.
        b (float): Denominator.

    Returns:
        float: The result.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

**Example of passing code:**
```python
def divide(a, b):
    """Divide two numbers.

    Args:
        a (float): Numerator.
        b (float): Denominator.

    Returns:
        float: The result.

    Raises:
        ValueError: If b is zero.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

**How to fix:** Add a `Raises:` section listing each exception the function may raise.

---

## Returns a Value Without `Returns:` Section

**Severity:** WARNING
**Category:** `returns`

**What it checks:** If the function has a `return <value>` statement (a return statement with a non-None value) but the docstring has no `Returns:` section, this fires.

**Example violation:**
```python
def double(x):
    """Double the input.

    Args:
        x (int): The value to double.
    """
    return x * 2
```

**How to fix:** Add a `Returns:` section.

---

## `Returns:` Section Without Return Value

**Severity:** INFO
**Category:** `returns`

**What it checks:** If the docstring has a `Returns:` section but the function has no `return <value>` statement (only a bare `return` or no return at all), this is flagged as an informational hint. This check is skipped for `__init__` methods.

**Example violation:**
```python
def log_message(msg):
    """Log a message.

    Args:
        msg (str): The message to log.

    Returns:
        None: This function does not return a value.
    """
    print(msg)
```

**How to fix:** Remove the `Returns:` section, or add a meaningful return value.

---

## Empty Docstring

**Severity:** ERROR
**Category:** `format`

**What it checks:** The docstring exists (as a string literal) but contains no text after stripping whitespace.

**Example violation:**
```python
def my_func():
    """"""
    pass
```

**How to fix:** Add at least a summary line.

---

## Missing Summary Line

**Severity:** ERROR
**Category:** `format`

**What it checks:** The first line of the docstring (after stripping) is empty.

**Example violation:**
```python
def my_func():
    """
    Args:
        None.
    """
    pass
```

**How to fix:** Add a summary on the very first line of the docstring, before any blank line.

---

## Non-Standard Section Header

**Severity:** INFO
**Category:** `format`

**What it checks:** Lines that look like section headers (capitalised, single word, ending with `:`) but are not in the official Google-style list are flagged.

**Recognised standard headers:**
`Args:`, `Returns:`, `Raises:`, `Yields:`, `Attributes:`, `Example:`, `Examples:`, `Note:`, `Notes:`

**Example violation:**
```python
def fetch(url):
    """Fetch data from a URL.

    Params:
        url (str): The URL to fetch.
    """
```

`Params:` is not a standard Google-style header; `Args:` should be used instead.

**How to fix:** Replace the non-standard header with the closest standard equivalent.

---

## Placeholder Text Found

**Severity:** WARNING
**Category:** `quality`

**What it checks:** The docstring contains any of these placeholder strings (case-insensitive): `TODO`, `FIXME`, `XXX`, `HACK`, `Description of`, `TBD`, `To be determined`.

> **Note:** The generated starter docstring includes `"Description of the return value."` in the `Returns:` section. The validator will flag this if you validate without updating it first. This is by design — it encourages you to write a real description.

**How to fix:** Replace placeholder text with actual documentation.

---

## Summary Line Too Short

**Severity:** INFO
**Category:** `quality`

**What it checks:** The summary line (first line of the docstring) is fewer than 10 characters.

**Example violation:**
```python
def save():
    """Save."""
    ...
```

**How to fix:** Write a more descriptive summary (at least 10 characters).

---

## Duplicate Parameter Descriptions

**Severity:** WARNING
**Category:** `quality`

**What it checks:** When a function has more than one parameter, all parameter descriptions in `Args:` must be unique. Copy-pasted descriptions are flagged.

**Example violation:**
```python
def copy(src, dst):
    """Copy a file.

    Args:
        src (str): Path to the file.
        dst (str): Path to the file.
    """
```

**How to fix:** Write a unique description for each parameter.

---

## Summary and Description Are Identical

**Severity:** INFO
**Category:** `quality`

**What it checks:** If the extended description (text between the summary and first section header) is identical to the summary line, the description is redundant.

**How to fix:** Either remove the description or expand it with additional detail beyond the summary.

---

## Related

- **[Python API](python-api.md)** — `DocstringValidator`, `ValidationReport`, `Severity` classes
- **[CLI Reference](cli-reference.md)** — `pycodecommenter validate` command and exit codes
- **[Recipes](recipes.md)** — using validation in CI/CD pipelines
