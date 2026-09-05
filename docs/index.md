---
title: PyCodeCommenter — Python Docstring Generator & Validator
description: >
  PyCodeCommenter automatically generates Google-style Python docstrings,
  validates them against real function signatures, and measures documentation
  coverage. Deterministic, AST-based, no AI. Works in CI/CD pipelines.
keywords: python docstring generator, docstring validator, documentation coverage, google style docstrings, python documentation tool, AST parser, CI/CD documentation
---

# PyCodeCommenter — Python Docstring Generator & Validator

<div class="pcc-hero">
  <div class="pcc-hero__logo" aria-hidden="true">
    <svg viewBox="0 0 120 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line class="pcc-ast-line" x1="60" y1="16" x2="30" y2="50" stroke="#0284C7" stroke-width="3" stroke-linecap="round"/>
      <line class="pcc-ast-line" x1="60" y1="16" x2="90" y2="50" stroke="#0284C7" stroke-width="3" stroke-linecap="round"/>
      <line class="pcc-ast-line" x1="30" y1="50" x2="16" y2="84" stroke="#3B82C4" stroke-width="2.5" stroke-linecap="round"/>
      <line class="pcc-ast-line" x1="30" y1="50" x2="46" y2="84" stroke="#3B82C4" stroke-width="2.5" stroke-linecap="round"/>
      <line class="pcc-ast-line" x1="90" y1="50" x2="74" y2="84" stroke="#3B82C4" stroke-width="2.5" stroke-linecap="round"/>
      <line class="pcc-ast-line" x1="90" y1="50" x2="104" y2="84" stroke="#3B82C4" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="60" cy="16" r="7" fill="#0284C7"/>
      <circle cx="30" cy="50" r="6" fill="#5B9FD6"/>
      <circle cx="90" cy="50" r="6" fill="#5B9FD6"/>
      <circle cx="16" cy="84" r="5" fill="#94A3B8"/>
      <circle cx="46" cy="84" r="5" fill="#94A3B8"/>
      <circle cx="74" cy="84" r="5" fill="#94A3B8"/>
      <circle cx="104" cy="84" r="5" fill="#94A3B8"/>
    </svg>
  </div>
  <h2>Keep Python docstrings accurate as your code evolves.</h2>
  <p class="pcc-hero__tagline">
    Deterministic docstring generation and validation for production Python.
    No AI guesswork — just reliable, rule-based inference that syncs your docs with your AST.
  </p>
</div>

---

## What is PyCodeCommenter?

**PyCodeCommenter** is an open-source Python tool that:

1. **Generates** Google-style docstrings from your code's AST — no AI, no guesswork.
2. **Validates** existing docstrings against real function signatures across six check categories.
3. **Measures** documentation coverage per file and across entire projects.
4. **Exports** structured JSON for integration with any downstream tooling.

Install with: `pip install pycodecommenter` · Requires Python 3.9+

---

## The Problem & The Solution

**Before PyCodeCommenter:** Code changes, but docstrings don't.
```python
def process_data(items, strict=False):
    return items  # 'strict' isn't documented anywhere
```

**After PyCodeCommenter:** Run `$ pycodecommenter generate <path/to/your_file.py>` to instantly sync the skeleton — names, types, and defaults, always accurate because they're extracted, not guessed. What the tool can't extract (what `process_data` actually *means*) is left as an explicit `TODO(pycodecommenter): describe` marker for you to fill in, not a guessed sentence.
```python
def process_data(items, strict=False):
    """Process data.

    TODO(pycodecommenter): describe

    Args:
        items (Any): TODO(pycodecommenter): describe.
        strict (Any): Default is false. (default: False)

    Returns:
        Any: TODO(pycodecommenter): describe
    """
    return items
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
pycodecommenter generate <path/to/your_file.py> --dry-run
```

Ready to apply? Write docstrings directly into the file:

```bash
pycodecommenter generate <path/to/your_file.py> --inplace
```

Validate and get a JSON report:

```bash
pycodecommenter validate <path/to/your_file.py> --output-format json
```

---

## 3. Explore the Documentation

<div class="pcc-nav-cards">

<a class="pcc-card" href="getting-started/">
  <span class="pcc-card__icon">▸</span>
  <span class="pcc-card__title">Getting Started</span>
  <span class="pcc-card__desc">Step-by-step from install to your first generate, validate, and coverage run.</span>
</a>

<a class="pcc-card" href="validation-checks/">
  <span class="pcc-card__icon">✓</span>
  <span class="pcc-card__title">Validation Checks</span>
  <span class="pcc-card__desc">All checks — severity levels, violation examples, and how to fix each one.</span>
</a>

<a class="pcc-card" href="recipes/">
  <span class="pcc-card__icon">⟲</span>
  <span class="pcc-card__title">Recipes & CI</span>
  <span class="pcc-card__desc">Pre-commit hooks, GitHub Actions, and coverage gating patterns.</span>
</a>

<a class="pcc-card" href="cli-reference/">
  <span class="pcc-card__icon">›_</span>
  <span class="pcc-card__title">CLI Reference</span>
  <span class="pcc-card__desc">Every flag and argument for generate, validate, and coverage — derived directly from the source.</span>
</a>

<a class="pcc-card" href="python-api/">
  <span class="pcc-card__icon">{ }</span>
  <span class="pcc-card__title">Python API</span>
  <span class="pcc-card__desc">Use PyCodeCommenter programmatically: PyCodeCommenter, DocstringValidator, CoverageAnalyzer.</span>
</a>

<a class="pcc-card" href="faq/">
  <span class="pcc-card__icon">?</span>
  <span class="pcc-card__title">FAQ</span>
  <span class="pcc-card__desc">Common questions answered directly from the source code.</span>
</a>

</div>

---

## Key Facts

| Property | Value |
|---|---|
| PyPI package | `pycodecommenter` |
| Import name | `PyCodeCommenter` |
| Python support | 3.9, 3.10, 3.11, 3.12 |
| Output docstring style | Google |
| Input parsing | Google (full), Sphinx (full), NumPy (full) |
| AI / LLM dependency | None — fully deterministic |
| Runtime dependencies | `ruamel.yaml` (config), `libcst` (patching) |
| License | MIT |
| Version | v2.5.0 |

---

## Links

- **PyPI**: [pypi.org/project/pycodecommenter](https://pypi.org/project/pycodecommenter/)
- **GitHub**: [github.com/AmosQuety/PyCodeCommenter](https://github.com/AmosQuety/PyCodeCommenter)
- **Issues**: [github.com/AmosQuety/PyCodeCommenter/issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
- **Creator**: [Nabasa Amos (Amos Quety)](https://nabasa-amos.netlify.app)

<!-- JSON-LD structured data for AI engines and search crawlers -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "PyCodeCommenter",
  "alternateName": "pycodecommenter",
  "description": "Open-source Python tool for automatically generating Google-style docstrings, validating docstrings against real function signatures, and measuring documentation coverage. Deterministic, AST-based, no AI required.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Linux, macOS, Windows",
  "url": "https://amosquety.github.io/PyCodeCommenter/",
  "downloadUrl": "https://pypi.org/project/pycodecommenter/",
  "codeRepository": "https://github.com/AmosQuety/PyCodeCommenter",
  "version": "2.5.0",
  "license": "https://opensource.org/licenses/MIT",
  "programmingLanguage": "Python",
  "runtimePlatform": "Python 3.9+",
  "keywords": "python, docstring, documentation, validation, coverage, google-style, AST, CI/CD",
  "author": {
    "@type": "Person",
    "name": "Nabasa Amos",
    "alternateName": "Amos Quety",
    "url": "https://nabasa-amos.netlify.app",
    "sameAs": [
      "https://github.com/AmosQuety",
      "https://linkedin.com/in/nabasa-amos"
    ]
  },
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  }
}
</script>
