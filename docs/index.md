# PyCodeCommenter

<div class="pcc-hero">
  <div class="pcc-hero__logo">&lt;/&gt;</div>
  <!-- Replace the placeholder above with an <img> tag once docs/assets/logo.png is added:
       <img src="assets/logo.png" alt="PyCodeCommenter logo" width="80" height="80"> -->
  <p class="pcc-hero__tagline">
    Automatically generate, validate, and maintain Google-style docstrings
    for Python code — deterministic, fast, no API calls.
  </p>
</div>

> Automatically generate, validate, and maintain Google-style docstrings for Python code — without AI, without guessing.

PyCodeCommenter is a deterministic, rule-based docstring tool for Python developers who want accurate documentation that stays in sync with their code.

---

## Why PyCodeCommenter?

**Three things set it apart from every other docstring tool:**

1. **Deterministic, not generative.** Every description is derived from the function name, parameter names, and type annotations using a fixed rule chain — no LLM, no network calls, no randomness. The same input always produces the same output.

2. **Validation that actually checks your code.** The validator reads your AST and cross-references every parameter name, return annotation, and raised exception against what is written in the docstring. It catches drift that code review misses.

3. **Coverage metrics for documentation.** Just like a test coverage tool tells you which lines are untested, PyCodeCommenter tells you which functions and classes are undocumented — across a single file or an entire project.

---

## Installation

```bash
pip install pycodecommenter
```

Requires **Python 3.8 or later**.

---

## First Run

Generate docstrings for a Python file and preview the changes before writing anything:

```bash
pycodecommenter generate mymodule.py --dry-run
```

This prints a unified diff showing exactly what would be inserted. When you are happy, write the changes:

```bash
pycodecommenter generate mymodule.py --inplace
```

---

## Explore the documentation

<div class="pcc-nav-cards">

<a class="pcc-card" href="getting-started/">
  <span class="pcc-card__title">Getting Started</span>
  <span class="pcc-card__desc">Step-by-step from install to your first generate, validate, and coverage run.</span>
</a>

<a class="pcc-card" href="cli-reference/">
  <span class="pcc-card__title">CLI Reference</span>
  <span class="pcc-card__desc">Every subcommand, flag, argument, and exit code — exhaustive and exact.</span>
</a>

<a class="pcc-card" href="python-api/">
  <span class="pcc-card__title">Python API</span>
  <span class="pcc-card__desc">Use PyCodeCommenter programmatically from your own Python code.</span>
</a>

<a class="pcc-card" href="configuration/">
  <span class="pcc-card__title">Configuration</span>
  <span class="pcc-card__desc">.pycodecommenter.yaml key reference and auto-discovery behaviour.</span>
</a>

<a class="pcc-card" href="validation-checks/">
  <span class="pcc-card__title">Validation Checks</span>
  <span class="pcc-card__desc">All 18 checks — severity, violation examples, and how to fix each one.</span>
</a>

<a class="pcc-card" href="docstring-styles/">
  <span class="pcc-card__title">Docstring Styles</span>
  <span class="pcc-card__desc">Google (generated), Sphinx (parsed), NumPy (roadmap) — honest about gaps.</span>
</a>

<a class="pcc-card" href="recipes/">
  <span class="pcc-card__title">Recipes</span>
  <span class="pcc-card__desc">Pre-commit hooks, GitHub Actions, coverage gating — copy-paste ready.</span>
</a>

<a class="pcc-card" href="contributing/">
  <span class="pcc-card__title">Contributing</span>
  <span class="pcc-card__desc">How to report bugs, propose features, and submit pull requests.</span>
</a>

</div>

---

## Links

- **PyPI**: [pypi.org/project/pycodecommenter](https://pypi.org/project/pycodecommenter/)
- **GitHub**: [github.com/AmosQuety/PyCodeCommenter](https://github.com/AmosQuety/PyCodeCommenter)
- **Issues**: [github.com/AmosQuety/PyCodeCommenter/issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
