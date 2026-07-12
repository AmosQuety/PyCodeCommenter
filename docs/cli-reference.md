---
title: CLI Reference — PyCodeCommenter generate, validate, coverage
description: Complete CLI reference for PyCodeCommenter. Documents every flag for the generate, validate, and coverage subcommands including --output-format json for machine-readable output.
keywords: pycodecommenter cli, python docstring cli, validate docstrings command line, documentation coverage cli, json output
---

# CLI Reference

The PyCodeCommenter command-line interface provides three subcommands: `generate`, `validate`, and `coverage`. This page documents every argument and flag for each, derived directly from `cli.py`.

The entry point is installed as `pycodecommenter` when you run `pip install pycodecommenter`.

---

## pycodecommenter generate

Reads a Python source file, generates Google-style docstrings for every undocumented function and class, and either prints, saves, or patches the result.

If a function or class already has a docstring, the existing content is **merged**, not discarded. The existing summary, parameter descriptions, and return description are preserved and used as the base; only missing sections are filled in.

### Usage

```bash
pycodecommenter generate <file> [options]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to the Python source file to process |

### Options / Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-i`, `--inplace` | flag | off | Modify the file in place. Without this flag or `--output`, the result is printed to stdout |
| `-o`, `--output` | string | none | Write the result to this file path instead of stdout |
| `--dry-run` | flag | off | Print a unified diff of what would change and exit. Does **not** write any files. Exits with code 1 if there are changes, 0 if the file is already fully documented |
| `--backup` | flag | off | Before modifying the file in place, copy it to `<file>.bak`. Has no effect without `--inplace` (a warning is printed) |

### Output modes (mutually used in order)

1. If `--dry-run` is given, always print a diff and exit. No other flag matters.
2. If `--inplace` is given, write back to the original file (and create `.bak` if `--backup` is set).
3. If `--output <path>` is given (without `--inplace`), write to the specified path.
4. If none of the above, print the result to stdout.

### Examples

**Preview what would be added (safe, no writes):**
```bash
pycodecommenter generate mymodule.py --dry-run
```

**Write docstrings directly into the file:**
```bash
pycodecommenter generate mymodule.py --inplace
```

**Create a backup first, then patch:**
```bash
pycodecommenter generate mymodule.py --inplace --backup
```

**Write to a separate output file:**
```bash
pycodecommenter generate mymodule.py --output mymodule_documented.py
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — file processed (or, in `--dry-run` mode, no changes detected) |
| `1` | Parse error — file could not be read or parsed (in `--dry-run` mode: changes were detected) |

---

## pycodecommenter validate

Reads a Python source file and checks every function and class docstring for consistency with the actual code. Prints a structured report to the console.

### Usage

```bash
pycodecommenter validate <file>
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to the Python source file to validate |

### Options / Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output-format` | `text` \| `json` | `text` | Output format. `text` prints the human-readable report (default). `json` prints a machine-readable JSON object to stdout. |

### What the validator checks

Six categories of checks are run on every documented function:

1. **Signature matching** — every parameter in the function signature must appear in the `Args:` section, and vice versa.
2. **Type consistency** — if a parameter has a type annotation and is not in the docstring, that is flagged.
3. **Exception documentation** — if the function body contains `raise` statements, a `Raises:` section is expected (Google or Sphinx style).
4. **Return documentation** — if the function has a `return <value>` statement, a `Returns:` section is expected, and vice versa.
5. **Format compliance** — the docstring must have a summary line; non-standard section headers are flagged.
6. **Content quality** — placeholder text (`TODO`, `FIXME`, `Description of`, etc.), very short summaries, and duplicate parameter descriptions are flagged.

### Output format

**Text mode (default):**
```
============================================================
VALIDATION REPORT
============================================================
File: mymodule.py
Coverage: 75.0%
Total Issues: 3
  - Errors: 1
  - Warnings: 2
  - Info: 0

ISSUES:

[ERROR] mymodule.py:12:process_data: Parameter 'timeout' is not documented in docstring
  → Suggestion: Add 'timeout' to the Args section
```

**JSON mode (`--output-format json`):**
```json
{
  "file": "mymodule.py",
  "stats": {
    "total": 3,
    "errors": 1,
    "warnings": 2,
    "info": 0,
    "coverage_percentage": 75.0
  },
  "issues": [
    {
      "line": 12,
      "severity": "ERROR",
      "check": "signature",
      "message": "Parameter 'timeout' is not documented in docstring"
    }
  ]
}
```

### Examples

**Validate a single file:**
```bash
pycodecommenter validate src/api.py
```

**Use in a shell script with exit code check:**
```bash
pycodecommenter validate src/api.py && echo "All good"
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No ERROR-level issues found (warnings and info do not trigger a non-zero exit) |
| `1` | One or more ERROR-level issues were found |

---

## pycodecommenter coverage

Analyzes documentation coverage for a Python file or an entire directory tree.

### Usage

```bash
pycodecommenter coverage <path> [options]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `path` | Yes | A Python file or a directory to analyze recursively |

### Options / Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-e`, `--exclude` | list | none | One or more patterns to exclude. Paths containing any of these strings are skipped. Built-in defaults when not provided: `__pycache__`, `.git`, `venv`, `tests`, `test_` |
| `--output-format` | `text` \| `json` | `text` | Output format. `text` prints the human-readable coverage table. `json` prints a machine-readable JSON object to stdout. |

> **Note:** The `--exclude` patterns are matched by checking whether the pattern string appears anywhere in the file path. They are not full glob expressions — they are simple substring matches.

### Output

**Directory mode** prints a per-file table followed by a project total:

```
================================================================================
DOCUMENTATION COVERAGE REPORT
================================================================================
[OK] api.py                                                 100.0%
[!!] utils.py                                                50.0%
[!!] models.py                                                0.0%
--------------------------------------------------------------------------------
TOTAL                                                        60.0%
================================================================================
```

**Single file mode** prints one line:

```
Coverage for src/api.py: 87.5%
```

### Examples

**Analyze a whole project:**
```bash
pycodecommenter coverage .
```

**Analyze only the `src` subdirectory:**
```bash
pycodecommenter coverage ./src
```

**Exclude test and migration files:**
```bash
pycodecommenter coverage . --exclude tests migrations
```

**Analyze a single file:**
```bash
pycodecommenter coverage src/api.py
```

### Exit Codes

The `coverage` subcommand always exits with code 0. There is no built-in threshold enforcement in the CLI — use the Python API (`CoverageAnalyzer`) to implement threshold gating.

| Code | Meaning |
|------|---------|
| `0` | Analysis complete (regardless of coverage percentage) |

---

## Global behaviour

If `pycodecommenter` is called with no subcommand, or with an unrecognised subcommand, it prints the top-level help message and exits with code 0.

```bash
pycodecommenter
# prints usage and subcommand list
```

---

## Related

- **[Getting Started](getting-started.md)** — walkthrough with real examples
- **[Python API](python-api.md)** — programmatic access to the same functionality
- **[Recipes](recipes.md)** — complete CI/CD and pre-commit integrations
