# FAQ

Answers to common questions about PyCodeCommenter, based on what the source code actually does.

---

## Does PyCodeCommenter work with async functions?

**Yes, fully.** Both `async def` functions and regular `def` functions are handled identically by the generator, the validator, and the coverage analyser.

The `DocstringVisitor` class has a `visit_AsyncFunctionDef` method that processes `async def` the same way as `visit_FunctionDef`. The validator's `validate_all()` method checks `isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))` in both the traversal and the individual check methods.

```python
# This works correctly
async def fetch_data(url: str) -> dict:
    ...

commenter = PyCodeCommenter().from_string(code)
patched = commenter.get_patched_code()
```

---

## Will it overwrite my hand-written docstrings?

**No — existing content is preserved and merged.**

When `get_patched_code()` encounters a function or class that already has a docstring, it does not discard it. Instead:

1. `DocstringParser` reads the existing docstring and extracts the summary, description, parameter descriptions, and return description.
2. Those extracted values are used as the base for the new docstring.
3. Only missing pieces (undocumented parameters, missing `Returns:` section) are filled in with generated text.
4. The result is written back in place of the original docstring.

What this means in practice: if you wrote a good summary and parameter descriptions, they will survive a re-run of `generate --inplace`. The tool only fills in what is absent.

One important exception: the **return description** is always replaced with `"Description of the return value."` if the existing docstring's `Returns:` content is absent. If you have already written a return description, it will be preserved.

---

## What Python versions are supported?

**Python 3.8, 3.9, 3.10, 3.11, and 3.12.**

From `pyproject.toml`:

```toml
requires-python = ">=3.8"
```

Python 2.x is not supported and will not be.

---

## Does it support NumPy or Sphinx style?

**Sphinx: partially. NumPy: not at all.**

| Style | Input (parsing) | Output (generation) |
|-------|----------------|---------------------|
| Google | Full | Full — the only output format |
| Sphinx | Partial — extracts summary, `:param`, `:return:` | Not generated |
| NumPy | Not supported | Not generated |

**Sphinx:** The `DocstringParser` detects Sphinx-style docstrings (by checking for `:param` or `:return:` in the body) and extracts summary, parameters, and return description. Other Sphinx directives (`:type:`, `:rtype:`, `:raises:`) are silently ignored. The output, after `generate --inplace`, will be converted to Google style.

**NumPy:** NumPy-style docstrings (sections separated by underline dashes) are not detected or parsed. They will be treated as an unstructured description block, which means no parameter descriptions will be extracted and they will all be regenerated from scratch.

NumPy support is on the project roadmap.

---

## Can I use it in CI without it failing my build?

**Yes — exit codes are designed for CI use.**

| Subcommand | Exits 1 when | Exits 0 when |
|------------|-------------|-------------|
| `generate --dry-run` | There are missing/different docstrings | File is already fully documented |
| `generate` (no dry-run) | File cannot be parsed | Generation succeeded |
| `validate` | Any ERROR-level issue is found | No ERRORs (warnings and info are allowed) |
| `coverage` | Never | Always |

**WARNING** and **INFO** issues from `validate` do **not** cause a non-zero exit. Only `Severity.ERROR` issues do. This means you can use `validate` in CI to enforce a baseline (all functions documented, no orphaned params) without blocking on style suggestions.

For coverage threshold enforcement, use the Python API — the `coverage` CLI subcommand does not have a `--fail-below` flag yet.

---

## How is it different from AI docstring generators?

PyCodeCommenter is **deterministic and rule-based**. Given the same input, it always produces the same output. There are no API calls, no network requests, and no rate limits.

The tradeoff is that the generated descriptions are functional starting points, not polished prose. The tool excels at:

- **Structure** — correct Args/Returns/Raises sections with the right parameters
- **Type extraction** — reading annotations and inferring types from expressions
- **Preservation** — keeping your hand-written text when you re-run

It is not designed to write eloquent explanations. Think of it as a scaffolding tool that gives you the right structure and populates what it can deterministically; you fill in the meaning.

---

## What does the coverage percentage measure exactly?

The percentage is:

```
(documented_functions + documented_classes)
────────────────────────────────────────── × 100
(total_functions + total_classes)
```

A function or class counts as **documented** if and only if its first body statement is a string literal (i.e., `ast.get_docstring(node)` returns a non-empty string).

From `coverage.py`:

```python
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        coverage.total_functions += 1
        if ast.get_docstring(node):
            coverage.documented_functions += 1
    elif isinstance(node, ast.ClassDef):
        coverage.total_classes += 1
        if ast.get_docstring(node):
            coverage.documented_classes += 1
```

**What is not counted:**
- Module-level docstrings (the string at the top of a `.py` file)
- Inline comments
- Variable annotations or type stubs

**What counts as documented regardless of quality:**
- Any non-empty docstring — even a single word. The validator checks quality; the coverage tool only checks presence.

---

## Can I run it on a whole project at once?

**Coverage analysis: yes.** `pycodecommenter coverage <directory>` and `CoverageAnalyzer.analyze_directory()` both walk an entire directory tree recursively.

**Generation: one file at a time via the CLI.** `pycodecommenter generate` takes a single file argument. To process a whole project, use a shell loop:

```bash
# Bash
for f in $(find ./src -name "*.py"); do
    pycodecommenter generate "$f" --inplace
done
```

Or use the Python API to iterate yourself:

```python
from pathlib import Path
from PyCodeCommenter import PyCodeCommenter

for py_file in Path("./src").rglob("*.py"):
    commenter = PyCodeCommenter().from_file(str(py_file))
    if commenter.parsed_code:
        patched = commenter.get_patched_code()
        py_file.write_text(patched, encoding="utf-8")
```

**Validation: one file at a time via the CLI.** The `validate` subcommand also takes a single file. The pre-commit framework handles the per-file invocation automatically (see [Recipes](recipes.md)).

---

## Why does my `Returns:` always say "Description of the return value."?

This is a known placeholder inserted by the generator. The rule-based engine can infer the **type** of the return value (from the annotation or by analysing `return` statements), but it cannot infer the **meaning** of what is returned.

After running `generate --inplace`, you should search for `"Description of the return value."` and replace each instance with a real description. The validator's `check_content_quality` check will flag this text with a WARNING (because `"Description of"` is in its placeholder list).

---

## Related

- **[Getting Started](getting-started.md)** — step-by-step first use
- **[Validation Checks](validation-checks.md)** — full list of what the validator checks
- **[Recipes](recipes.md)** — CI/CD patterns
- **[Configuration](configuration.md)** — `.pycodecommenter.yaml` reference
