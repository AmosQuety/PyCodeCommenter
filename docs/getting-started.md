# Getting Started

Welcome to PyCodeCommenter. This page walks you through everything you need to go from a fresh install to running your first generation, validation, and coverage check. No prior experience with docstring tools is required — if you know Python, you are ready.

---

## 1. Installation

Install PyCodeCommenter from PyPI:

```bash
pip install pycodecommenter
```

**Python version requirement:** Python 3.8 or later (as declared in `pyproject.toml`: `requires-python = ">=3.8"`).

Verify the install:

```bash
pycodecommenter --help
```

You should see a list of available subcommands: `generate`, `validate`, and `coverage`.

---

## 2. Your First Docstring

### Step 1 — Create a sample file

Create a file called `sample.py` with an undocumented function:

```python
# sample.py

def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)

class ShoppingCart:
    def __init__(self, items: list):
        self.items = items

    def add_item(self, item):
        self.items.append(item)
```

### Step 2 — Preview the changes with `--dry-run`

Before writing anything, use `--dry-run` to see the diff of what PyCodeCommenter would insert:

```bash
pycodecommenter generate sample.py --dry-run
```

This prints a unified diff to the terminal. No file is modified. If changes exist, the command exits with code 1; if the file is already fully documented, it exits with code 0.

Example output:

```diff
--- sample.py
+++ sample.py
@@ -1,9 +1,28 @@
 def calculate_discount(price: float, rate: float = 0.1) -> float:
+    """Calculate discount.
+
+    Calculates the discount.
+
+    Args:
+        price (float): float value.
+        rate (float): float value. Default is 0.1.
+
+    Returns:
+        float: Description of the return value.
+    """
     return price * (1 - rate)
```

### Step 3 — Write the changes in place

When the diff looks correct, apply the docstrings directly to the file:

```bash
pycodecommenter generate sample.py --inplace
```

If you want a safety copy first:

```bash
pycodecommenter generate sample.py --inplace --backup
```

This creates `sample.py.bak` before modifying `sample.py`.

### Step 4 — Write to a different file instead

You can also write the result to a new file without touching the original:

```bash
pycodecommenter generate sample.py --output sample_documented.py
```

### Before and after

**Before:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)
```

**After `pycodecommenter generate sample.py --inplace`:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    """Calculate discount.

    Calculates the discount.

    Args:
        price (float): float value.
        rate (float): float value. Default is 0.1.

    Returns:
        float: Description of the return value.
    """
    return price * (1 - rate)
```

> **Note:** The generated summary and parameter descriptions are rule-based starting points. You should review and refine them — especially the `Returns` description, which always starts as "Description of the return value." The goal is to give you a correct structure, not a finished document.

---

## 3. Your First Validation

Once you have documented code, you can validate whether the docstrings are consistent with the actual code:

```bash
pycodecommenter validate sample.py
```

The validator reads the file, walks the AST, and checks every function and class docstring for six types of issues:

- **Missing docstrings** (ERROR)
- **Signature mismatches** — params in code not in docs, or docs mentioning params that don't exist (ERROR / WARNING)
- **Type consistency** — annotated params not documented (INFO)
- **Exception documentation** — raised exceptions not in a `Raises:` section (WARNING)
- **Return documentation** — function returns a value but docstring has no `Returns:` section (WARNING)
- **Format compliance** — non-standard section headers (INFO)
- **Content quality** — placeholder text like "TODO", "Description of", very short summaries (WARNING / INFO)

**Example output for a well-documented file:**

```
============================================================
VALIDATION REPORT
============================================================
File: sample.py
Coverage: 100.0%
Total Issues: 1
  - Errors: 0
  - Warnings: 1
  - Info: 0

ISSUES:

[WARNING] sample.py:7:calculate_discount: Function returns a value but has no Returns section in docstring
  → Suggestion: Add a Returns section documenting the return value
```

**Exit codes:**
- `0` — no ERROR-level issues (warnings and info do not cause a non-zero exit)
- `1` — one or more ERROR-level issues found

---

## 4. Your First Coverage Report

Coverage analysis tells you what percentage of your functions and classes have docstrings. Run it on a directory:

```bash
pycodecommenter coverage ./src
```

Or on a single file:

```bash
pycodecommenter coverage sample.py
```

**Example output (directory):**

```
================================================================================
DOCUMENTATION COVERAGE REPORT
================================================================================
[OK] sample.py                                              100.0%
[!!] utils.py                                               33.3%
[!!] models.py                                               0.0%
--------------------------------------------------------------------------------
TOTAL                                                        44.4%
================================================================================
```

- `[OK]` — 100% coverage
- `[!!]` — one or more items are undocumented

**What counts as "documented"?**

A function or class counts as documented if it has a Python docstring — the first statement of its body is a string literal. The percentage is calculated as:

```
(documented_functions + documented_classes) / (total_functions + total_classes) × 100
```

**Excluding patterns:**

By default the analyzer skips paths matching `__pycache__`, `.git`, `venv`, `tests`, and `test_`. You can override with `--exclude`:

```bash
pycodecommenter coverage . --exclude migrations vendor
```

---

## 5. Next Steps

- **[CLI Reference](cli-reference.md)** — complete list of every flag for every subcommand
- **[Python API](python-api.md)** — use PyCodeCommenter from Python code instead of the command line
- **[Configuration](configuration.md)** — set up a `.pycodecommenter.yaml` in your project root
- **[Recipes](recipes.md)** — pre-commit hooks, GitHub Actions, and coverage gating workflows
