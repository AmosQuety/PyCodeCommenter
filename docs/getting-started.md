---
title: Getting Started — PyCodeCommenter Python Docstring Generator
description: Install PyCodeCommenter and generate your first Google-style Python docstrings in under two minutes. Step-by-step guide for generate, validate, and coverage commands.
keywords: install pycodecommenter, python docstring generator tutorial, how to generate docstrings python, getting started
---

# Getting Started

Welcome to PyCodeCommenter. This guide will get you from zero to fully documented code in under two minutes.

---

## 1. Install

We recommend installing PyCodeCommenter inside an active virtual environment so it doesn't conflict with system packages.

```bash
pip install pycodecommenter
```

*Requires Python 3.10 or later.*

Verify the installation:

```bash
pycodecommenter --version
```

---

## 2. Run

You don't need to configure anything to run PyCodeCommenter. You just need to point it at a specific Python file.

We recommend running it in **dry-run** mode first. This allows you to preview the changes safely in your terminal without modifying your actual files:

```bash
pycodecommenter generate <path/to/your_file.py> --dry-run
```

> [!TIP]
> **Important:** Replace `<path/to/your_file.py>` with the actual name and location of the file you want to document (for example, `main.py` or `src/utils.py`). You can use relative or absolute paths.

Once you've reviewed the proposed docstrings and are happy with them, tell PyCodeCommenter to write the changes directly into your file:

```bash
pycodecommenter generate <path/to/your_file.py> --inplace
```

---

## 3. Tutorial: one file, start to finish

This walk-through takes one small file through every command. Everything shown below is real output. Save this as `pricing.py`:

```python
def discounted_price(price: float, rate: float = 0.1) -> float:
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    return price * (1 - rate)


def is_eligible(age: int, member: bool = False) -> bool:
    return member or age >= 65
```

### Step 1. Measure where you start

```bash
pycodecommenter coverage pricing.py
```

```text
Coverage for pricing.py: 0.0%
```

`pycodecommenter validate pricing.py` reports two errors, one per function: `Function 'discounted_price' has no docstring` and the same for `is_eligible`. It exits with code `1`.

### Step 2. Preview what will be written

```bash
pycodecommenter generate pricing.py --dry-run
```

The run prints a summary on stderr and the changes as a diff on stdout:

```text
Summary: 2 docstrings would be written.
  2 details taken straight from the code
  1 gap left as "TODO(pycodecommenter)" for you to fill
Next: fill the gaps with `pycodecommenter review`, or add --ai-draft to have them drafted; then run `pycodecommenter validate`.
```

Nothing is changed. (`--dry-run` exits with code `1` when there would be changes, `0` when there would be none, so it can gate a CI job.)

### Step 3. Write the docstrings

```bash
pycodecommenter generate pricing.py --inplace
```

This is what the tool worked out from the code alone:

```python
def discounted_price(price: float, rate: float = 0.1) -> float:
    """Discounted price.

    Args:
        price (float): float value.
        rate (float): float value. (default: 0.1)

    Returns:
        float: TODO(pycodecommenter): describe

    Raises:
        ValueError: If `not 0 <= rate <= 1`.
    """
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    return price * (1 - rate)


def is_eligible(age: int, member: bool = False) -> bool:
    """Is eligible.

    Args:
        age (int): int value.
        member (bool): Boolean flag. (default: False)

    Returns:
        bool: True if `member or age >= 65`, otherwise False.
    """
    return member or age >= 65
```

Look at what is and isn't stated. The types, the defaults, the `ValueError` and the condition that raises it (`not 0 <= rate <= 1`) and what `is_eligible` returns are read straight from the code, so they are exact. What `discounted_price` returns is something only a person can say, so the tool leaves an explicit `TODO(pycodecommenter): describe` marker instead of guessing. The summaries (`Discounted price.`) and descriptions such as `float value.` are only what the names and types say; improve them when they are worth improving.

### Step 4. Fill the gaps

```bash
pycodecommenter review pricing.py --list
```

```text
pricing.py:9  gap  in discounted_price(): float: TODO(pycodecommenter): describe

0 AI-drafted lines, 1 gap, 0 repeated comments to review in 1 file. Run `pycodecommenter review` in a terminal to go through them.
```

In a terminal, `pycodecommenter review pricing.py` asks about each item:

```text
pricing.py: 1 item to review

pricing.py:9 in discounted_price(): 
  gap: float: TODO(pycodecommenter): describe
[f]ill, [s]kip, [q]uit: f
New text: The price after the discount is taken off.

Saved pricing.py: 1 filled.
```

Before it saves, `review` checks that only docstrings and comments changed, so it can't damage your code. You can also edit the marker by hand.

### Step 5. Check the result

```bash
pycodecommenter validate pricing.py
```

```text
File: pricing.py
Coverage: 100.0%
Total Issues: 0
  - Errors: 0
  - Warnings: 0
  - Info: 0
```

```bash
pycodecommenter coverage pricing.py
```

```text
Coverage for pricing.py: 100.0%
```

From here, `validate` keeps the docstrings honest as the code changes: rename a parameter, or add a `raise`, and it tells you which docstring no longer matches. See [Recipes](recipes.md) to run it in CI.

> [!NOTE]
> By default PyCodeCommenter is deterministic and makes no network calls. The `TODO(pycodecommenter): describe` markers are a to-do list, not finished documentation: fill them in with `pycodecommenter review`, or add `--ai-draft` to have an AI model draft them (every drafted line is labelled `(AI-drafted, unreviewed)`). `pycodecommenter validate --fail-on-todo` fails while any are left.

---

## 4. Common Options

PyCodeCommenter includes four subcommands: `generate`, `review`, `validate` and `coverage`.

### Generate Documentation
Generate or update docstrings for a Python file.
```bash
# Create backups before modifying
pycodecommenter generate <path/to/your_file.py> --inplace --backup

# Write the result to a new file instead of modifying the original
pycodecommenter generate <path/to/your_file.py> --output <path/to/new_file.py>
```

### Validate Documentation
Check if existing docstrings are accurate and match the code's signature.
```bash
pycodecommenter validate src/
```
*Exits with code `1` if there are missing arguments or type mismatches in the docstrings.*

### Check Coverage
Get a percentage report of how much of your codebase is documented.
```bash
pycodecommenter coverage src/
```

---

## 5. Next Steps

Now that you have it running, integrate it into your workflow:

- **[Configuration](configuration.md)** — set up a `.pycodecommenter.yaml` to save your CLI flags.
- **[Validation Checks](validation-checks.md)** — understand exactly what the validator looks for.
- **[Recipes & CI](recipes.md)** — copy-paste our GitHub Actions and pre-commit hooks to enforce documentation automatically.
