# PyCodeCommenter

<div class="pcc-hero">
  <div class="pcc-hero__logo">&lt;/&gt;</div>
  <h2>Keep Python docstrings accurate as your code evolves.</h2>
  <p class="pcc-hero__tagline">
    Deterministic docstring generation and validation for production Python. No AI guesswork—just reliable, rule-based inference that syncs your docs with your AST.
  </p>
</div>

---

## The Problem & The Solution

**Before PyCodeCommenter:** Code changes, but docstrings don't.
```python
def process_data(items, strict=False):
    # Missing 'strict' in docstring. No return type documented.
```

**After PyCodeCommenter:** Run `$ pycodecommenter generate src/mymodule.py` to instantly sync them.
```python
def process_data(items, strict=False):
    """
    Process data.

    Args:
        items: The items to process.
        strict: Whether to use strict processing.

    Returns:
        The processed data.
    """
```

---

## 1. Install

```bash
pip install pycodecommenter
```

---

## 2. Run

Preview the changes PyCodeCommenter will make to your project without writing to disk:

```bash
pycodecommenter generate src/mymodule.py --dry-run
```

Ready to format? Apply the changes:

```bash
pycodecommenter generate src/mymodule.py --inplace
```

---

## 3. Explore the Documentation

<div class="pcc-nav-cards">

<a class="pcc-card" href="getting-started/">
  <span class="pcc-card__title">Getting Started</span>
  <span class="pcc-card__desc">Step-by-step from install to your first generate, validate, and coverage run.</span>
</a>

<a class="pcc-card" href="validation-checks/">
  <span class="pcc-card__title">Validation Checks</span>
  <span class="pcc-card__desc">All 18 checks — severity, violation examples, and how to fix each one.</span>
</a>

<a class="pcc-card" href="recipes/">
  <span class="pcc-card__title">Recipes & CI</span>
  <span class="pcc-card__desc">Pre-commit hooks, GitHub Actions, and coverage gating.</span>
</a>

<a class="pcc-card" href="configuration/">
  <span class="pcc-card__title">Configuration</span>
  <span class="pcc-card__desc">.pycodecommenter.yaml key reference and auto-discovery behaviour.</span>
</a>

</div>

---

## Links

- **PyPI**: [pypi.org/project/pycodecommenter](https://pypi.org/project/pycodecommenter/)
- **GitHub**: [github.com/AmosQuety/PyCodeCommenter](https://github.com/AmosQuety/PyCodeCommenter)
- **Issues**: [github.com/AmosQuety/PyCodeCommenter/issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
