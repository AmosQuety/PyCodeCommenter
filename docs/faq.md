---
title: PyCodeCommenter FAQ — Python Docstring Generator & Validator
description: >
  Frequently asked questions about PyCodeCommenter: how it works, what Python versions it supports,
  how it compares to AI docstring generators, and how to use it in CI/CD pipelines.
keywords: pycodecommenter faq, python docstring generator questions, docstring validator help, documentation coverage python
---

# FAQ

Answers to common questions about PyCodeCommenter, based directly on what the source code does.

---

## What is PyCodeCommenter?

**PyCodeCommenter** is an open-source Python tool that automatically generates Google-style docstrings, validates existing docstrings against real function signatures, and measures documentation coverage across Python projects.

It works entirely on your local machine — no AI, no API calls, no rate limits. Install with `pip install pycodecommenter`.

---

## How do I install PyCodeCommenter?

```bash
pip install pycodecommenter
```

Python 3.8 or later is required. After install, the `pycodecommenter` command is available on your PATH.

---

## Does PyCodeCommenter use AI or LLMs?

**No.** PyCodeCommenter is fully deterministic. It uses Python's built-in `ast` module to parse source files and infer docstring structure from parameter names, type annotations, and function bodies. Given the same input, it always produces the same output.

There are no API calls, no network requests, no rate limits, and no AI model dependency.

---

## How is PyCodeCommenter different from AI docstring generators?

PyCodeCommenter is **deterministic and rule-based**. AI docstring generators send your code to an external API and return generated prose; PyCodeCommenter uses only your local AST.

The tradeoffs:

| Property | PyCodeCommenter | AI generators |
|---|---|---|
| Deterministic output | ✅ Yes | ❌ No |
| Network required | ❌ No | ✅ Yes |
| Rate limits | ❌ No | ✅ Yes |
| Cost | ✅ Free | Often paid |
| Prose quality | Functional starting point | Richer prose |
| Signature accuracy | ✅ Always correct | Can hallucinate |
| Validation | ✅ Built-in | Rarely included |

PyCodeCommenter excels at structural correctness — right parameters, right types, right sections — not at generating eloquent prose.

---

## Does PyCodeCommenter work with async functions?

**Yes, fully.** Both `async def` and regular `def` functions are handled identically by the generator, validator, and coverage analyser.

```python
async def fetch_data(url: str) -> dict:
    ...

commenter = PyCodeCommenter().from_string(code)
patched = commenter.get_patched_code()
```

---

## Will it overwrite my hand-written docstrings?

**No — existing content is preserved and merged.**

When `get_patched_code()` encounters a function that already has a docstring:

1. `DocstringParser` reads the existing docstring and extracts the summary, description, parameter descriptions, and return description.
2. Those extracted values are used as the base for the new docstring.
3. Only missing pieces are filled in with generated text.
4. The result is written back in place of the original docstring.

If you wrote a good summary and parameter descriptions, they will survive a re-run of `generate --inplace`. The tool only fills in what is absent.

---

## What Python versions does PyCodeCommenter support?

**Python 3.8, 3.9, 3.10, 3.11, and 3.12.**

```toml
requires-python = ">=3.8"
```

Python 2.x is not supported and will not be.

---

## What is documentation drift?

Documentation drift is when code is updated but the corresponding docstrings are not. Parameters get added or renamed, return types change, and exceptions get added — but the docstring stays the same.

PyCodeCommenter detects drift via six validation checks:

1. **Signature Matching** — params in code vs params in docstring.
2. **Type Consistency** — type annotations vs documented types.
3. **Exception Documentation** — `raise` statements vs `Raises:` section.
4. **Return Documentation** — `return value` vs `Returns:` section.
5. **Format Compliance** — summary line presence, section header validity.
6. **Content Quality** — placeholder text, short summaries, duplicate descriptions.

---

## Does it support NumPy or Sphinx style?

**Sphinx: partially. NumPy: not yet.**

| Style | Input (parsing) | Output (generation) |
|---|---|---|
| Google | Full | Full — the only output format |
| Sphinx | Partial — extracts summary, `:param`, `:return:`, `:raises:` | Not generated |
| NumPy | Not supported | Not generated |

NumPy support is on the project roadmap.

---

## Can I use PyCodeCommenter in CI/CD?

**Yes — exit codes are designed for CI use.**

| Subcommand | Exits 1 when | Exits 0 when |
|---|---|---|
| `generate --dry-run` | Changes would be made | File is already fully documented |
| `generate` | File cannot be parsed | Generation succeeded |
| `validate` | Any ERROR-level issue is found | No ERRORs (warnings and info are allowed) |
| `coverage` | Never | Always |

`WARNING` and `INFO` issues from `validate` do **not** cause a non-zero exit. Only `Severity.ERROR` issues do.

---

## How do I get JSON output from PyCodeCommenter?

Both `validate` and `coverage` support `--output-format json`:

```bash
pycodecommenter validate src/api.py --output-format json
pycodecommenter coverage ./src --output-format json
```

The `validate` JSON shape:

```json
{
  "file": "src/api.py",
  "stats": {
    "total": 3,
    "errors": 1,
    "warnings": 2,
    "info": 0,
    "coverage_percentage": 85.0
  },
  "issues": [
    {
      "line": 42,
      "severity": "ERROR",
      "check": "signature",
      "message": "Parameter 'timeout' is not documented in docstring"
    }
  ]
}
```

---

## How does PyCodeCommenter measure documentation coverage?

Coverage is:

```
(documented_functions + documented_classes)
────────────────────────────────────────── × 100
(total_functions + total_classes)
```

A function or class counts as **documented** if and only if its first body statement is a string literal (`ast.get_docstring(node)` returns a non-empty string).

**What is not counted:** module-level docstrings, inline comments, variable annotations.

**What counts as documented regardless of quality:** any non-empty docstring — even a single word. The validator checks quality; coverage only checks presence.

---

## Can I run PyCodeCommenter on a whole project at once?

**Coverage analysis: yes.** `pycodecommenter coverage <directory>` and `CoverageAnalyzer.analyze_directory()` walk an entire directory tree recursively.

**Generation: one file at a time via the CLI.** To batch-process a project:

```bash
for f in $(find ./src -name "*.py"); do
    pycodecommenter generate "$f" --inplace
done
```

Or via the Python API:

```python
from pathlib import Path
from PyCodeCommenter import PyCodeCommenter

for py_file in Path("./src").rglob("*.py"):
    commenter = PyCodeCommenter().from_file(str(py_file))
    if commenter.parsed_code:
        py_file.write_text(commenter.get_patched_code(), encoding="utf-8")
```

---

## Why does my `Returns:` always say "Description of the return value."?

This is a known placeholder. The rule-based engine can infer the **type** of the return value but cannot infer the **meaning** of what is returned.

After running `generate --inplace`, search for `"Description of the return value."` and replace each instance with a real description. The validator's `check_content_quality` check will flag this text with a WARNING (because `"Description of"` is in its placeholder list).

---

## Does PyCodeCommenter handle decorators correctly?

**Yes, as of v2.2.0:**

- `@property` getter — return check fires as normal.
- `@property` setter / deleter — return check is skipped (no false-positive warning).
- `@classmethod` — `cls` is excluded from parameter checks automatically.
- `@staticmethod` — all declared parameters are validated normally.

---

## Related

- **[Getting Started](getting-started.md)** — step-by-step first use
- **[Validation Checks](validation-checks.md)** — full list of what the validator checks
- **[CLI Reference](cli-reference.md)** — every flag and argument
- **[Recipes](recipes.md)** — CI/CD patterns
- **[Configuration](configuration.md)** — `.pycodecommenter.yaml` reference
