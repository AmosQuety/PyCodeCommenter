# Getting Started

Welcome to PyCodeCommenter. This guide will get you from zero to fully documented code in under two minutes.

---

## 1. Install

Install PyCodeCommenter directly via pip:

```bash
pip install pycodecommenter
```

*Requires Python 3.8 or later.*

Verify the installation:

```bash
pycodecommenter --version
```

---

## 2. Run

You don't need to configure anything to run PyCodeCommenter. Point it at a Python file or directory. 

We recommend running it in **dry-run** mode first so you can preview the changes without modifying your files:

```bash
pycodecommenter generate . --dry-run
```

Once you've reviewed the proposed docstrings, write the changes to your files:

```bash
pycodecommenter generate . --inplace
```

---

## 3. Expected Output

When you run the tool, PyCodeCommenter parses your AST (Abstract Syntax Tree), infers the intent from your parameter names and type hints, and generates perfect Google-style docstrings.

**Before:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)
```

**After:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    """
    Calculate discount.

    Calculates the discount.

    Args:
        price (float): float value.
        rate (float): float value. Default is 0.1.

    Returns:
        float: Description of the return value.
    """
    return price * (1 - rate)
```

> [!NOTE]
> PyCodeCommenter is deterministic. It does not use AI or LLMs. It generates a structural starting point that guarantees you meet the syntax requirements of the Google docstring standard.

---

## 4. Common Options

PyCodeCommenter includes three primary subcommands.

### Generate Documentation
Generate or update docstrings for a file or directory.
```bash
# Create backups before modifying
pycodecommenter generate src/ --inplace --backup

# Exclude specific directories
pycodecommenter generate . --exclude tests/ vendor/
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
