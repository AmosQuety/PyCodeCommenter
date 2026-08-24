# Python API Reference

PyCodeCommenter exposes a clean Python API for all three of its core capabilities — generation, validation, and coverage analysis. This page documents every public class exported from the package.

All classes listed here are importable directly from the top-level package:

```python
from PyCodeCommenter import (
    PyCodeCommenter,
    DocstringValidator,
    ValidationReport,
    ValidationIssue,
    Severity,
    CoverageAnalyzer,
    FileCoverage,
    ProjectCoverage,
    TypeAnalyzer,
    DocstringParser,
)
```

---

## PyCodeCommenter

The main class for loading Python code, generating docstrings, and patching the source. All methods return `self` or a computed value, enabling a fluent interface.

### Constructor

```python
PyCodeCommenter()
```

No parameters. After construction, call `from_string()` or `from_file()` to load code.

| Attribute | Type | Description |
|-----------|------|-------------|
| `code` | `str` | The raw source code (set by `from_string` / `from_file`) |
| `parsed_code` | `ast.Module` or `None` | The parsed AST; `None` if parsing failed |
| `comments` | `list` | Populated by `generate_docstrings()` |
| `tokenized_comments` | `list` | Raw comment tokens extracted during load |
| `type_analyzer` | `TypeAnalyzer` | Instance used internally for type inference |

### Methods

---

#### from_string(code_string) -> PyCodeCommenter

Load code from a string. Returns `self` so calls can be chained.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `code_string` | `str` | A string containing valid Python source code |

**Returns:** `PyCodeCommenter` (the same instance)

**Raises:** Does not raise. Logs a warning on empty input; logs an error on `SyntaxError` and sets `parsed_code = None`.

**Example:**

```python
from PyCodeCommenter import PyCodeCommenter

code = """
def greet(name: str) -> str:
    return f"Hello, {name}"
"""

commenter = PyCodeCommenter().from_string(code)
```

---

#### from_file(file_path) -> PyCodeCommenter

Load code from a file on disk. Returns `self`.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `str` | Absolute or relative path to a Python `.py` file |

**Returns:** `PyCodeCommenter` (the same instance)

**Raises:** Does not raise. Logs an error and sets `parsed_code = None` on `FileNotFoundError`, `IOError`, or `SyntaxError`.

**Example:**

```python
commenter = PyCodeCommenter().from_file("src/api.py")
if not commenter.parsed_code:
    print("Could not parse the file")
```

---

#### generate_docstrings() -> list

Walk the AST and generate docstring strings for every function and class. Returns a flat list of generated docstring strings (one per node). Does not modify the source.

**Parameters:** None

**Returns:** `list` of `str` — one entry per function/class found (including module docstring if present)

**Example:**

```python
commenter = PyCodeCommenter().from_string(code)
docstrings = commenter.generate_docstrings()
for doc in docstrings:
    print(doc)
```

---

#### get_patched_code() -> str

Return the full source code with all docstrings inserted or replaced. If a function or class already has a docstring, it is **updated** (the existing summary, parameter descriptions, and return text are preserved). New docstrings are inserted at the correct indentation level.

**Parameters:** None

**Returns:** `str` — the complete patched source code

**Example:**

```python
commenter = PyCodeCommenter().from_string(code)
patched = commenter.get_patched_code()
print(patched)

# Write to disk yourself:
with open("output.py", "w", encoding="utf-8") as f:
    f.write(patched)
```

---

#### validate(strict=False) -> ValidationReport

Validate all docstrings in the loaded code against the actual AST signatures. Returns a full `ValidationReport`.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `strict` | `bool` | `False` | Parameter is accepted but does not yet affect behaviour. Reserved for future use |

**Returns:** `ValidationReport`

**Raises:** Does not raise. Returns an empty `ValidationReport` if `parsed_code` is `None`.

**Example:**

```python
import sys
from PyCodeCommenter import PyCodeCommenter

commenter = PyCodeCommenter().from_file("src/api.py")
report = commenter.validate()
report.print_summary()

if report.stats.errors > 0:
    sys.exit(1)
```

---

#### check_coverage() -> FileCoverage

Calculate documentation coverage for the loaded code.

**Parameters:** None

**Returns:** `FileCoverage` — coverage stats for the in-memory code (path is set to `"<string>"`)

**Example:**

```python
commenter = PyCodeCommenter().from_string(code)
coverage = commenter.check_coverage()
print(f"{coverage.coverage_percentage:.1f}%")
print(f"Functions: {coverage.documented_functions}/{coverage.total_functions}")
print(f"Classes:   {coverage.documented_classes}/{coverage.total_classes}")
```

---

## DocstringValidator

Validates an existing Python source file or code string for documentation quality.

### Constructor

```python
DocstringValidator(code_string=None, file_path=None)
```

Provide exactly one of the two parameters.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code_string` | `str` or `None` | `None` | Python source code as a string |
| `file_path` | `str` or `None` | `None` | Path to a `.py` file to read and validate |

If both are provided, `code_string` takes precedence.

**Example:**

```python
from PyCodeCommenter import DocstringValidator

# From string
validator = DocstringValidator(code_string=my_code)

# From file
validator = DocstringValidator(file_path="src/models.py")
```

### Methods

---

#### validate_all() -> ValidationReport

Run all six validation checks across all functions and classes in the parsed code.

**Returns:** `ValidationReport`

**Example:**

```python
validator = DocstringValidator(file_path="src/models.py")
report = validator.validate_all()
report.print_summary()
```

---

#### check_signature_match(func_node, docstring, location) -> List[ValidationIssue]

Check that every parameter in the function signature is documented and every documented parameter exists in the signature.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `func_node` | `ast.FunctionDef` or `ast.AsyncFunctionDef` | The function AST node |
| `docstring` | `str` | The raw docstring text |
| `location` | `str` | Location string for issue reporting, e.g. `"file.py:10:my_func"` |

**Returns:** `List[ValidationIssue]`

---

#### check_type_consistency(func_node, docstring, location) -> List[ValidationIssue]

Check that annotated parameters and return types are reflected in the docstring.

**Parameters:** Same structure as `check_signature_match`.

**Returns:** `List[ValidationIssue]`

---

#### check_exception_documentation(func_node, docstring, location) -> List[ValidationIssue]

Check that any `raise` statements in the function body are matched by a recognised Raises section in the docstring — Google-style `Raises:`, a bare `Raises` header, or Sphinx-style `:raises `.

**Parameters:** Same structure as `check_signature_match`.

**Returns:** `List[ValidationIssue]`

---

#### check_return_documentation(func_node, docstring, location) -> List[ValidationIssue]

Check that `return <value>` statements are matched by a `Returns:` section and vice versa.

**Parameters:** Same structure as `check_signature_match`.

**Returns:** `List[ValidationIssue]`

---

#### check_format_compliance(docstring, location) -> List[ValidationIssue]

Check that the docstring has a summary line and only uses recognised Google-style section headers.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `docstring` | `str` | The raw docstring text |
| `location` | `str` | Location string for issue reporting |

**Returns:** `List[ValidationIssue]`

---

#### check_content_quality(docstring, location) -> List[ValidationIssue]

Check for placeholder text, very short summaries, and duplicate parameter descriptions.

**Parameters:** Same as `check_format_compliance`.

**Returns:** `List[ValidationIssue]`

---

## ValidationReport

Container for the results of a `validate_all()` run.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `issues` | `List[ValidationIssue]` | All issues found |
| `stats` | `ValidationStats` | Aggregated statistics |
| `file_path` | `str` or `None` | Source file path, if applicable |

### Methods

---

#### add_issue(issue) -> None

Add a `ValidationIssue` to the report and update `stats` counters.

---

#### print_summary() -> None

Print a human-readable summary of the report to stdout, including all issues and suggestions.

---

#### to_dict() -> dict

Return the report as a Python dictionary, suitable for JSON serialisation.

**Example:**

```python
import json
report_dict = report.to_dict()
with open("report.json", "w") as f:
    json.dump(report_dict, f, indent=2)
```

---

#### to_markdown() -> str

Return the report as a Markdown-formatted string.

**Example:**

```python
with open("report.md", "w") as f:
    f.write(report.to_markdown())
```

---

## ValidationStats

Dataclass holding aggregated counts from a validation run. Accessed via `report.stats`.

| Field | Type | Description |
|-------|------|-------------|
| `total_functions` | `int` | Total functions encountered |
| `total_classes` | `int` | Total classes encountered |
| `documented_functions` | `int` | Functions with a docstring |
| `documented_classes` | `int` | Classes with a docstring |
| `total_issues` | `int` | Total issues found |
| `errors` | `int` | ERROR-level issue count |
| `warnings` | `int` | WARNING-level issue count |
| `info` | `int` | INFO-level issue count (renamed from `infos` in v2.3.0 to match the `"info"` key in JSON/Markdown output; `.infos` still works as a backward-compatible property alias) |
| `coverage_percentage` | `float` (property) | `(documented / total) * 100` |

---

## ValidationIssue

Dataclass representing a single documentation problem.

| Field | Type | Description |
|-------|------|-------------|
| `severity` | `Severity` | `Severity.ERROR`, `Severity.WARNING`, or `Severity.INFO` |
| `category` | `str` | One of `"missing"`, `"signature"`, `"types"`, `"exceptions"`, `"returns"`, `"format"`, `"quality"` |
| `location` | `str` | `"file.py:line:function_name"` |
| `message` | `str` | Human-readable description of the issue |
| `suggestion` | `str` or `None` | How to fix the issue |

---

## Severity

Enum for issue severity levels.

```python
from PyCodeCommenter import Severity

Severity.ERROR    # value: "error"   — Must fix; causes exit code 1
Severity.WARNING  # value: "warning" — Should fix; does not affect exit code
Severity.INFO     # value: "info"    — Nice to have; does not affect exit code
```

---

## CoverageAnalyzer

Analyses documentation coverage for individual files or entire directory trees.

### Constructor

```python
CoverageAnalyzer()
```

No parameters.

### Methods

---

#### analyze_file(file_path) -> FileCoverage

Analyse a single Python source file.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `str` | Path to the `.py` file |

**Returns:** `FileCoverage`

**Example:**

```python
from PyCodeCommenter import CoverageAnalyzer

analyzer = CoverageAnalyzer()
coverage = analyzer.analyze_file("src/api.py")
print(f"{coverage.coverage_percentage:.1f}%")
```

---

#### analyze_directory(directory, exclude_patterns=None) -> ProjectCoverage

Recursively analyse all `.py` files in a directory.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `directory` | `str` | — | Path to the directory to analyse |
| `exclude_patterns` | `List[str]` or `None` | `None` | Extra patterns to exclude, added to the built-in defaults (`__pycache__`, `.git`, `.venv`, `venv`, `env`, `.tox`, `.nox`, `__pypackages__`, `site-packages`, `build`, `dist`, `.eggs`, `.egg-info`, `.mypy_cache`, `.pytest_cache`, `node_modules`, `tests`, `test_`) — never a replacement for them. A pattern matches a path component exactly, plus a dot-prefixed pattern (e.g. `.egg-info`) also matches a component it's a suffix of, and an underscore-suffixed pattern (e.g. `test_`) also matches a component it's a prefix of; it is not a substring match against the whole path |

**Returns:** `ProjectCoverage`

**Example:**

```python
analyzer = CoverageAnalyzer()
project = analyzer.analyze_directory("./src", exclude_patterns=["migrations"])
project.print_report()

if project.total_coverage < 80.0:
    print(f"Coverage {project.total_coverage:.1f}% is below threshold")
```

---

## FileCoverage

Dataclass holding coverage statistics for one file.

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Path to the file |
| `total_functions` | `int` | Total functions found |
| `documented_functions` | `int` | Functions with docstrings |
| `total_classes` | `int` | Total classes found |
| `documented_classes` | `int` | Classes with docstrings |
| `coverage_percentage` | `float` (property) | `(documented / total) * 100` |

---

## ProjectCoverage

Dataclass holding coverage statistics across all analysed files.

| Field | Type | Description |
|-------|------|-------------|
| `files` | `Dict[str, FileCoverage]` | Mapping of file path to its `FileCoverage` |
| `total_coverage` | `float` (property) | Aggregate coverage across all files |

### Methods

---

#### print_report() -> None

Print a formatted coverage table to stdout.

---

#### to_json() -> dict

Export coverage data as a dictionary.

```python
import json
data = project.to_json()
with open("coverage.json", "w") as f:
    json.dump(data, f, indent=2)
```

---

## shields_badge_dict

A standalone function, not a class — imported from the `coverage` submodule directly (it isn't in the top-level `PyCodeCommenter` package `__all__`):

```python
from PyCodeCommenter.coverage import shields_badge_dict
```

#### shields_badge_dict(percentage, label="docs coverage") -> dict

Build a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge) dict for a coverage percentage. This is what backs the `coverage` CLI command's `--badge-output` flag.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `percentage` | `float` | — | Coverage percentage, 0-100 |
| `label` | `str` | `"docs coverage"` | Badge label text |

**Returns:** `dict` with `schemaVersion`, `label`, `message`, and `color` keys. `color` is `brightgreen` at ≥90%, `green` at ≥75%, `yellow` at ≥50%, and `red` below that.

**Example:**

```python
import json
from PyCodeCommenter import CoverageAnalyzer
from PyCodeCommenter.coverage import shields_badge_dict

project = CoverageAnalyzer().analyze_directory("./src")
badge = shields_badge_dict(project.total_coverage)
with open("coverage_badge.json", "w") as f:
    json.dump(badge, f, indent=2)
```

---

## TypeAnalyzer

Infers Python types from AST nodes. Used internally by `PyCodeCommenter` during docstring generation. Exposed publicly for advanced programmatic use.

### Constructor

```python
TypeAnalyzer(local_types=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `local_types` | `Dict[str, str]` or `None` | `{}` | Pre-known variable-to-type mappings for the current scope |

### Key Methods

#### infer_type(node) -> str

Infer type for an `ast.arg` node (with annotation) or any expression node.

#### infer_expr_type(expr) -> str

Infer type from an expression node (literal, list, dict, binary op, call, etc.).

#### get_annotation_type(annotation) -> str

Translate an annotation AST node (supports PEP 604 `|` and PEP 585 generics) into a readable string such as `"List[str]"` or `"Union[int, str]"`.

---

## DocstringParser

Parses existing Google-style or Sphinx-style docstrings into structured components. Used internally during the merge step of `get_patched_code()`.

### Constructor

```python
DocstringParser(docstring=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `docstring` | `str` or `None` | `""` | The raw docstring text to parse. Parsing happens immediately on construction |

### Attributes (after construction)

| Attribute | Type | Description |
|-----------|------|-------------|
| `summary` | `str` | First line of the docstring |
| `description` | `str` | Body text before the first section header |
| `params` | `Dict[str, str]` | Mapping of parameter name to its description |
| `returns` | `str` | Content of the `Returns:` section |

### Methods

---

#### get_info() -> dict

Return all parsed components as a dictionary.

```python
{
    "summary": "...",
    "description": "...",
    "params": {"name": "description", ...},
    "returns": "..."
}
```

**Example:**

```python
from PyCodeCommenter import DocstringParser

docstring = """Process the data.

Args:
    data (str): The data to process.

Returns:
    str: The processed result.
"""

parser = DocstringParser(docstring)
info = parser.get_info()
print(info["summary"])      # "Process the data."
print(info["params"])       # {"data": "The data to process."}
print(info["returns"])      # "str: The processed result."
```

---

## Related

- **[CLI Reference](cli-reference.md)** — the command-line interface for all the same operations
- **[Validation Checks](validation-checks.md)** — detailed descriptions of every check run by `DocstringValidator`
- **[Recipes](recipes.md)** — complete CI/CD examples using the Python API
