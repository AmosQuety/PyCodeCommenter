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

*Requires Python 3.9 or later.*

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

## 3. Expected Output

When you run the tool, PyCodeCommenter parses your AST (Abstract Syntax Tree) and generates a Google-style docstring skeleton from what it can actually extract: parameter names, type hints, and default values. Anything it can't extract — what a parameter or function actually *means* — is left as an explicit `TODO(pycodecommenter): describe` marker for you to fill in, not guessed at.

**Before:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)
```

**After:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    """Calculate discount.

    TODO(pycodecommenter): describe

    Args:
        price (float): float value.
        rate (float): float value. (default: 0.1)

    Returns:
        float: TODO(pycodecommenter): describe
    """
    return price * (1 - rate)
```

> [!NOTE]
> PyCodeCommenter is deterministic. It does not use AI or LLMs. The Args/Returns skeleton (names, types, defaults) is always accurate, since it's extracted, not guessed. The `TODO(pycodecommenter): describe` markers above are exactly that — a to-do list, not finished documentation — and `pycodecommenter validate` will flag any left unresolved (see [Recipes](recipes.md)).

---

## 4. Common Options

PyCodeCommenter includes three primary subcommands.

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
