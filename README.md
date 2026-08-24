# PyCodeCommenter — Python Docstring Generator & Validator

[![PyPI version](https://badge.fury.io/py/pycodecommenter.svg)](https://pypi.org/project/pycodecommenter/)
[![Documentation](https://img.shields.io/badge/docs-amosquety.github.io%2FPyCodeCommenter-blue)](https://amosquety.github.io/PyCodeCommenter/)
[![Python Support](https://img.shields.io/pypi/pyversions/pycodecommenter.svg)](https://pypi.org/project/pycodecommenter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docs Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/AmosQuety/PyCodeCommenter/main/coverage_badge.json)](https://github.com/AmosQuety/PyCodeCommenter)
[![GitHub Stars](https://img.shields.io/github/stars/AmosQuety/PyCodeCommenter?style=social)](https://github.com/AmosQuety/PyCodeCommenter)

**PyCodeCommenter** is an open-source Python docstring generator and documentation validator. It automatically generates Google-style docstrings from Python AST, validates existing docstrings against real function signatures, measures documentation coverage, and integrates with CI/CD pipelines — all with zero network calls and zero AI dependency.

> **Install:** `pip install pycodecommenter` · **Python 3.9+** · **MIT License**

---

## What PyCodeCommenter Does

| Task | Command |
|---|---|
| Generate missing docstrings | `pycodecommenter generate myfile.py --inplace` |
| Validate docstrings vs code | `pycodecommenter validate myfile.py` |
| Measure documentation coverage | `pycodecommenter coverage ./src` |
| JSON output for downstream tools | `pycodecommenter validate myfile.py --output-format json` |

**PyCodeCommenter** solves *documentation drift* — the common Python project problem where code changes but docstrings don't. It catches undocumented parameters, missing `Returns:` sections, orphaned docstring entries, and mismatched type hints before they reach production.

---

## Quick Start

```bash
pip install pycodecommenter

# Preview what will be added (safe, no writes)
pycodecommenter generate main.py --dry-run

# Apply docstrings in place
pycodecommenter generate main.py --inplace

# Validate accuracy
pycodecommenter validate main.py

# Check project coverage
pycodecommenter coverage ./src
```

---

## Why PyCodeCommenter?

### The Problem

- Code changes quickly; docstrings lag behind and become stale.
- No easy way to validate existing docstrings against real signatures.
- AI tools generate inconsistent or hallucinated documentation.
- Most Python projects have no coverage metric for documentation quality.

### The Solution

PyCodeCommenter uses **deterministic, AST-based analysis** — not AI — to:

- Generate structurally correct Google-style docstrings from your code's own AST. The Args/Returns/Attributes *skeleton* (names, types, defaults) is always accurate, since it's extracted, not guessed — but prose PyCodeCommenter can't extract from the code itself (what a parameter or function actually *means*) is left as a marked placeholder, `TODO(pycodecommenter): describe`, for a human to fill in, not presented as finished documentation.
- Validate parameter names, type hints, exception documentation, and return values.
- Measure and enforce documentation coverage across an entire project.
- Export structured JSON reports for integration with any downstream tooling.

### Related Tools

PyCodeCommenter isn't alone in this space. [pydoclint](https://github.com/jsh9/pydoclint) checks Args/Returns/Yields/Raises against the actual function signature across Google, NumPy, and Sphinx styles, is actively maintained, and is fast — if you only need validation, it's a strong choice. [interrogate](https://github.com/econchick/interrogate) measures presence-only documentation coverage, the same metric shape as `coverage.py` here. PyCodeCommenter's actual differentiator is breadth in one place: it's the only one of the three that generates a docstring skeleton *and* validates *and* measures coverage, all through one importable Python API — not just a CLI or pre-commit hook.

---

## Features

### Six Validation Checks

Every documented function is checked for:

1. **Signature Matching** — every parameter in the function signature must appear in `Args:`, and vice versa.
2. **Type Consistency** — type annotations must match documented types.
3. **Exception Documentation** — `raise` statements require a `Raises:` section (Google or Sphinx style).
4. **Return Documentation** — `return <value>` requires a `Returns:` section.
5. **Format Compliance** — docstring must have a summary line; non-standard section headers are flagged.
6. **Content Quality** — placeholder text (`TODO`, `FIXME`, `Description of`), short summaries, and duplicate descriptions are caught.

### Decorator-Aware Validation (v2.2.0)

- `@property` getter — return check fires as normal.
- `@property` setter / deleter — return check is skipped (no false-positive warnings).
- `@classmethod` — `cls` is excluded from parameter checks.
- `@staticmethod` — no self/cls stripping; all parameters validated.

### Structured JSON Output (v2.2.0)

Both `validate` and `coverage` support `--output-format json` for machine-readable output:

```bash
pycodecommenter validate src/api.py --output-format json
```

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

### Modern Python Support

- Python 3.9, 3.10, 3.11, 3.12.
- `async def` functions.
- Complex type hints: `Union`, `Optional`, `Generic`, `list[int]`, `int | str`.
- PEP 604 unions, PEP 585 generics.

### Coverage Reporting

- Per-file coverage percentages.
- Project-wide totals.
- JSON, Markdown, and console output.
- CI/CD integration with exit codes.

---

## Usage Examples

### Example 1: Generate Docstrings

```python
from PyCodeCommenter import PyCodeCommenter

code = """
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)
"""

commenter = PyCodeCommenter().from_string(code)
print(commenter.get_patched_code())
```

**Output:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    """Calculate discount.

    Args:
        price (float): Price of the product.
        rate (float): Discount rate to apply. (default: 0.1)

    Returns:
        float: Discounted price after applying the rate.
    """
    return price * (1 - rate)
```

### Example 2: Validate in CI/CD

```python
import sys
from PyCodeCommenter import PyCodeCommenter

commenter = PyCodeCommenter().from_file("src/main.py")
report = commenter.validate()

if report.stats.errors > 0:
    report.print_summary()
    sys.exit(1)  # Fail the CI build

print(f"✓ Documentation validated: {report.stats.coverage_percentage:.1f}% coverage")
```

### Example 3: Enforce Coverage Threshold

```python
from PyCodeCommenter import CoverageAnalyzer

analyzer = CoverageAnalyzer()
project = analyzer.analyze_directory("./src", exclude_patterns=["tests"])

if project.total_coverage < 80.0:
    print(f"❌ Coverage {project.total_coverage:.1f}% is below the 80% threshold")
    project.print_report()
    sys.exit(1)

print(f"✓ Coverage {project.total_coverage:.1f}% meets the threshold")
```

### Example 4: JSON Export

```python
import json
from PyCodeCommenter import PyCodeCommenter

commenter = PyCodeCommenter().from_file("mycode.py")
report = commenter.validate()

with open("validation_report.json", "w") as f:
    json.dump(report.to_dict(), f, indent=2)
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/docs.yml
name: Documentation Check

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pycodecommenter
      - run: pycodecommenter validate src/
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-docstrings
        name: Validate Docstrings
        entry: pycodecommenter validate
        language: system
        types: [python]
```

---

## Frequently Asked Questions

**What is PyCodeCommenter?**
PyCodeCommenter is a Python command-line tool and library for automatically generating Google-style docstrings and validating existing docstrings against real function signatures.

**How do I install PyCodeCommenter?**
Run `pip install pycodecommenter`. Python 3.9 or later is required.

**Does PyCodeCommenter use AI or LLMs?**
No. PyCodeCommenter is fully deterministic. It uses Python's built-in `ast` module to parse code and generate documentation. There are no API calls, no network requests, and no rate limits.

**Does PyCodeCommenter overwrite my hand-written docstrings?**
No. Existing summaries, parameter descriptions, and return descriptions are preserved and merged. Only missing sections are filled in automatically.

**What docstring styles does PyCodeCommenter support?**
PyCodeCommenter generates Google-style docstrings. It can parse Google-style, Sphinx-style (`:param:`, `:type:`, `:returns:`, `:raises:`), and NumPy-style (`Parameters`/`Returns`/`Raises` with dash-underlined headers) as input.

**Can I use PyCodeCommenter in CI/CD?**
Yes. The `validate` subcommand exits with code `1` when any ERROR-level issue is found, making it suitable for blocking CI builds. The `--output-format json` flag enables integration with any downstream tooling.

**What is documentation drift?**
Documentation drift is when code is updated but the corresponding docstrings are not. Parameters get added or renamed, return types change, and exceptions get added — but the docstring stays the same. PyCodeCommenter detects and fixes this.

**How does PyCodeCommenter measure documentation coverage?**
Coverage is `(documented_functions + documented_classes) / (total_functions + total_classes) × 100`. A function counts as documented if its first body statement is a non-empty string literal.

---

## Configuration

Create `.pycodecommenter.yaml` in your project root:

```yaml
style: google
validation:
  level: strict
  check_types: true
  check_exceptions: true
coverage:
  threshold: 80
  fail_below: true
exclude:
  - "*/tests/*"
  - "*/migrations/*"
  - "*/__pycache__/*"
```

---

## Documentation

Full documentation: **[https://amosquety.github.io/PyCodeCommenter/](https://amosquety.github.io/PyCodeCommenter/)**

- [Getting Started](https://amosquety.github.io/PyCodeCommenter/getting-started/)
- [Validation Checks](https://amosquety.github.io/PyCodeCommenter/validation-checks/)
- [CLI Reference](https://amosquety.github.io/PyCodeCommenter/cli-reference/)
- [Python API](https://amosquety.github.io/PyCodeCommenter/python-api/)
- [Recipes & CI](https://amosquety.github.io/PyCodeCommenter/recipes/)
- [FAQ](https://amosquety.github.io/PyCodeCommenter/faq/)

---

## Supported Platforms & Environments

- **OS**: Linux, macOS, Windows
- **Python**: 3.9, 3.10, 3.11, 3.12
- **Environments**: local, CI/CD (GitHub Actions, GitLab CI, Jenkins), pre-commit hooks
- **Dependencies**: `ruamel.yaml` (config files), `libcst` (docstring patching) — no AI/LLM dependency

---

## Known Limitations

- Python 2.x is not supported (EOL).
- `match` statements (Python 3.10+) have basic support.
- Generated prose that can't be extracted from the AST (what a parameter or function *means*, as opposed to its name/type/default) is a marked placeholder, `TODO(pycodecommenter): describe`, not finished documentation — running `generate --inplace` will leave these markers in place for a human to fill in.

---

## Roadmap

- [ ] VS Code extension
- [ ] Smart docstring updates that preserve human-written content
- [ ] ~~Optional AI-powered description generation~~
  > **⚠️ CONSTRAINED — READ BEFORE TOUCHING.** A full cost/benefit review
  > (money, hallucination risk, non-determinism, source-code privacy, brand
  > cost) concluded this must NEVER be built as generate-and-write. If picked
  > up: AI output must never be `--inplace`-writable — it may ONLY ever be
  > emitted as a diff/preview a human deliberately applies, the same shape as
  > Mintlify's Workflows agent (drafts, opens a PR, never publishes directly).
  > A plain "generate docstrings with AI" implementation is explicitly the
  > wrong shape and should be rejected in review, not merged and fixed later.
- [x] NumPy and full Sphinx style support (v2.3.0)
- [ ] GitHub Action for automated documentation PRs
- [x] `--fail-below` flag for coverage threshold enforcement in CLI (v2.3.0)

---

## Creator

PyCodeCommenter was created and is actively maintained by **Nabasa Amos (Amos Quety)**, a software engineer focused on developer tooling, documentation automation, and software quality.

- **Portfolio**: [nabasa-amos.netlify.app](https://nabasa-amos.netlify.app)
- **GitHub**: [AmosQuety](https://github.com/AmosQuety)
- **LinkedIn**: [Nabasa Amos](https://linkedin.com/in/nabasa-amos)
- **Contact**: amosnabasa4@gmail.com

---

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

## Issues & Discussions

- **Bug reports**: [GitHub Issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
- **Questions & ideas**: [GitHub Discussions](https://github.com/AmosQuety/PyCodeCommenter/discussions)

---

*If PyCodeCommenter is useful in your workflow, a ⭐ on GitHub helps other Python developers discover it.*
