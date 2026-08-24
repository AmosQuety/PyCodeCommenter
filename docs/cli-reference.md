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

Reads a Python source file **or directory**, generates Google-style docstrings for every undocumented function and class, and either prints, saves, or patches the result. Given a directory, it recursively collects every `.py` file (skipping the built-in and `--exclude`d paths described below) and processes each one the same way it would a single file.

If a function or class already has a docstring, the existing content is **merged**, not discarded. The existing summary, parameter descriptions, and return description are preserved and used as the base; only missing sections are filled in.

### Usage

```bash
pycodecommenter generate <file-or-directory> [options]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to a Python source file, or a directory to process recursively |

### Options / Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-i`, `--inplace` | flag | off | Modify the file(s) in place. Without this flag or `--output`, the result is printed to stdout |
| `-o`, `--output` | string | none | Write the result to this file path instead of stdout. Single-file targets only — errors out if the target is a directory |
| `--dry-run` | flag | off | Print a unified diff of what would change and exit. Does **not** write any files. Exits with code 1 if there are changes, 0 if not |
| `--backup` | flag | off | Before modifying a file in place, copy it to `<file>.bak`. Has no effect without `--inplace` (a warning is printed) |
| `-e`, `--exclude` | list | `.pycodecommenter.yaml`'s top-level `exclude` list, if set | Patterns to exclude, added to the built-in defaults (directory targets only). Built-in defaults: `__pycache__`, `.git`, `.venv`, `venv`, `env`, `.tox`, `.nox`, `__pypackages__`, `site-packages`, `build`, `dist`, `.eggs`, `.egg-info`, `.mypy_cache`, `.pytest_cache`, `node_modules` |

> **Note:** An `--exclude` pattern matches a path component (directory or file name) exactly; a dot-prefixed pattern (e.g. `.egg-info`) also matches a component it's a suffix of (covers the `<name>.egg-info` convention). This is exact-component matching, not a substring check against the whole path — `rebuild_index.py` is not skipped just because it contains `build`, and `environment_config.py` is not skipped just because it contains `env`. (The `coverage` command's `-e`/`--exclude`, documented below, adds one more rule on top of these two — see its note.)

### Output modes (mutually used in order)

1. If `--dry-run` is given, always print a diff (per file, for a directory target) and exit. No other flag matters.
2. If `--inplace` is given, write back to the original file(s) (and create `.bak` per file if `--backup` is set).
3. If `--output <path>` is given (without `--inplace`, single-file targets only), write to the specified path.
4. If none of the above, print the result to stdout (per file, prefixed with `# File: <path>`, for a directory target).

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

**Patch every file in a directory, excluding migrations:**
```bash
pycodecommenter generate src/ --inplace --backup --exclude migrations
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — file(s) processed (or, in `--dry-run` mode, no changes detected) |
| `1` | Parse error — a file could not be read or parsed (in `--dry-run` mode: changes were detected). For a directory target, any file failing to parse is enough to exit `1`. |

---

## pycodecommenter validate

Reads a Python source file **or directory** and checks every function and class docstring for consistency with the actual code. Given a directory, it recursively validates every `.py` file it finds (skipping the same built-in and `--exclude`d paths `generate` does).

### Usage

```bash
pycodecommenter validate <file-or-directory>
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `file` | Yes | Path to a Python source file, or a directory to validate recursively |

### Options / Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-e`, `--exclude` | list | `.pycodecommenter.yaml`'s top-level `exclude` list, if set | Patterns to exclude, added to the built-in defaults (directory targets only) — same matching rules and defaults as `generate`'s `-e`/`--exclude`, above |
| `--output-format` | `text` \| `json` | `text` | Output format. `text` prints one human-readable report per file. `json` prints a single JSON array of per-file report objects to stdout for a directory target (a single object for a single-file target). |

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

**Validate an entire directory:**
```bash
pycodecommenter validate src/
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No ERROR-level issues found (warnings and info do not trigger a non-zero exit) |
| `1` | One or more ERROR-level issues were found. For a directory target, this is true if **any** file in the tree has an ERROR-level issue. |

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
| `-e`, `--exclude` | list | none | One or more patterns to exclude, added to the built-in defaults (they don't replace them). Built-in defaults when not provided: `__pycache__`, `.git`, `.venv`, `venv`, `env`, `.tox`, `.nox`, `__pypackages__`, `site-packages`, `build`, `dist`, `.eggs`, `.egg-info`, `.mypy_cache`, `.pytest_cache`, `node_modules`, `tests`, `test_` |
| `--output-format` | `text` \| `json` | `text` | Output format. `text` prints the human-readable coverage table. `json` prints a machine-readable JSON object to stdout. |
| `--fail-below` | float | none (or `coverage.threshold` from `.pycodecommenter.yaml`, if set) | Exit with code `1` if the overall coverage percentage is below `THRESHOLD` |
| `--badge-output` | path | none | Write a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge) JSON file for the coverage percentage to `PATH` |

> **Note:** An `--exclude` pattern matches a path component (directory or file name) exactly; a dot-prefixed pattern (e.g. `.egg-info`) also matches a component it's a suffix of, and an underscore-suffixed pattern (e.g. `test_`) also matches a component it's a prefix of. They are not glob expressions, and they are not arbitrary substring matches against the full path either — matching is per path component.

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

**`--badge-output`** writes a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge) JSON file, independent of `--output-format` (the text/JSON console output above is unaffected):

```json
{
  "schemaVersion": 1,
  "label": "docs coverage",
  "message": "78%",
  "color": "green"
}
```

`color` is `brightgreen` at ≥90%, `green` at ≥75%, `yellow` at ≥50%, and `red` below that.

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

| Code | Meaning |
|------|---------|
| `0` | Analysis complete, and either `--fail-below` was not given or coverage was at or above the threshold |
| `1` | `--fail-below THRESHOLD` was given and the overall coverage percentage is below it |

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
