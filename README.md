# PyCodeCommenter

[![PyPI version](https://badge.fury.io/py/pycodecommenter.svg)](https://pypi.org/project/pycodecommenter/)
[![Python Support](https://img.shields.io/pypi/pyversions/pycodecommenter.svg)](https://pypi.org/project/pycodecommenter/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/github/stars/AmosQuety/PyCodeCommenter?style=social)](https://github.com/AmosQuety/PyCodeCommenter)

PyCodeCommenter is a Python docstring generator and documentation validation tool for teams that want accurate, maintainable, Google-style docstrings.

Created and maintained by Nabasa Amos (Amos Quety), PyCodeCommenter helps Python developers automate documentation, measure documentation coverage, and keep code documentation aligned with evolving code signatures.

Unlike AI-based documentation tools, PyCodeCommenter uses deterministic, rule-based validation to catch documentation issues that are easy to miss in day-to-day development. It is built for Python developer tools workflows, CI/CD documentation validation, and long-term documentation quality.

## Why I Built PyCodeCommenter

I built PyCodeCommenter because documentation drift is a common problem in Python projects. Code changes quickly, but docstrings often lag behind, become inconsistent, or stop matching the actual function signature.

The goal was to create a practical code documentation tool that could:

- Generate clear Google-style docstrings from Python code.
- Validate existing documentation against real function and method signatures.
- Improve documentation coverage without adding heavy workflow overhead.
- Fit naturally into documentation automation and CI/CD documentation validation pipelines.

PyCodeCommenter is meant to be useful for individual developers, open-source maintainers, and teams that want a reliable Python docstring generator with documentation validation built in.

## Project Story

PyCodeCommenter started as a simple docstring generator. Early versions focused on turning Python functions into readable Google-style docstrings with minimal friction.

As the project evolved, Nabasa Amos (Amos Quety) expanded it into a broader documentation validation and coverage platform. That change made the tool more useful in real projects, where generated docs are only part of the problem and the larger challenge is keeping documentation accurate over time.

Today, PyCodeCommenter combines docstring generation, documentation validation, documentation coverage reporting, and CI/CD-ready checks in a single Python package.

## Why PyCodeCommenter?

### The Problem
- AI tools generate inconsistent documentation.
- There is no easy way to validate existing docstrings against code.
- Documentation drifts as code evolves.
- Many projects lack coverage metrics for documentation quality.

### The Solution
- Generate professional docstrings automatically.
- Validate existing docs against actual code signatures.
- Track documentation coverage across projects.
- Integrate with CI/CD pipelines.

### Terminal Usage
```bash
# Generate docstrings for a file
pycodecommenter generate main.py -i

# Validate documentation
pycodecommenter validate main.py

# Check project coverage
pycodecommenter coverage .
```

## Features

### Comprehensive Validation
Six types of validation checks:
- **Signature Matching**: Params in code match docstring.
- **Type Consistency**: Type hints match documented types.
- **Exception Documentation**: Raised exceptions are documented.
- **Return Documentation**: Return values are properly documented.
- **Format Compliance**: Follows Google-style guidelines.
- **Content Quality**: No placeholders or TODOs.

### Coverage Reporting
- Per-file coverage metrics.
- Project-wide statistics.
- Export to JSON, Markdown, or console.
- CI/CD integration ready.

### Modern Python Support
- Python 3.8+ support.
- Async functions (`async def`).
- Complex type hints (`Union`, `Optional`, `Generic`).
- PEP 604 unions (`int | str`).
- PEP 585 generics (`list[int]`).

### Developer-Friendly
- Beautiful console output.
- Actionable error messages.
- Multiple export formats.
- Fast AST-based analysis with no API calls.

## Usage Examples

### Example 1: Basic Generation
```python
from PyCodeCommenter import PyCodeCommenter

code = """
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)
"""

commenter = PyCodeCommenter().from_string(code)
docstrings = commenter.generate_docstrings()
print(commenter.get_patched_code())
```

**Output:**
```python
def calculate_discount(price: float, rate: float = 0.1) -> float:
    """Calculate discount.
    
    Calculates the discount.
    
    Args:
        price (float): Price of the object.
        rate (float): Rate of the object. (default: 0.1)
    
    Returns:
        float: Description of the return value.
    """
    return price * (1 - rate)
```

### Example 2: Validation in CI/CD
```python
# validate_docs.py
import sys
from PyCodeCommenter import PyCodeCommenter

commenter = PyCodeCommenter().from_file("src/main.py")
report = commenter.validate()

if report.stats.errors > 0:
    report.print_summary()
    sys.exit(1)  # Fail CI build

print(f"✓ Documentation validated: {report.stats.coverage_percentage:.1f}% coverage")
```

### Example 3: Coverage Enforcement
```python
from PyCodeCommenter import CoverageAnalyzer

analyzer = CoverageAnalyzer()
project = analyzer.analyze_directory("./src", exclude_patterns=['tests'])

if project.total_coverage < 80.0:
    print(f"❌ Coverage {project.total_coverage:.1f}% below threshold 80%")
    project.print_report()
    sys.exit(1)

print(f"✓ Coverage {project.total_coverage:.1f}% meets threshold")
```

### Example 4: Export Reports
```python
import json
from PyCodeCommenter import PyCodeCommenter

commenter = PyCodeCommenter().from_file("mycode.py")
report = commenter.validate()

# JSON export
with open("validation_report.json", "w") as f:
    json.dump(report.to_dict(), f, indent=2)

# Markdown export
with open("validation_report.md", "w") as f:
    f.write(report.to_markdown())
```

## Configuration
Create `.pycodecommenter.yaml` in your project root:
```yaml
style: google  # or 'numpy', 'sphinx'
validation:
  level: strict  # or 'moderate', 'lenient'
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

## Use Cases
### For Individual Developers
- Generate documentation for new functions quickly.
- Validate docs before committing.
- Track documentation coverage.

### For Teams
- Enforce documentation standards in CI/CD.
- Prevent PRs with undocumented code.
- Maintain consistent documentation style.

### For Open Source Projects
- Welcome contributors with clear doc requirements.
- Run automated documentation checks in PRs.
- Publish public coverage badges.

## Integration

### Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-docstrings
        name: Validate Docstrings
        entry: pycodecommenter validate .
        language: system
        types: [python]
```

### GitHub Actions
```yaml
# .github/workflows/docs.yml
name: Documentation Check

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install pycodecommenter
      - name: Validate documentation
        run: pycodecommenter validate .
```

## Documentation
- **User Guide** - Comprehensive usage guide.
- **API Reference** - Complete API documentation.
- **Configuration** - Configuration options.
- **Contributing** - How to contribute.

## Known Limitations
- Does not support Python 2.x (EOL).
- Match statements (Python 3.10+) have basic support.
- Complex decorators may affect docstring placement.

## Roadmap
- [ ] VS Code extension
- [ ] Smart docstring updates that preserve human content
- [ ] AI-powered generation (optional)
- [ ] NumPy and Sphinx style support
- [ ] GitHub Action for automated PRs

## Creator

PyCodeCommenter was created and is actively maintained by **Nabasa Amos (Amos Quety)**, a software engineer focused on developer tooling, AI systems, and software quality.

The project was built to solve a common problem in Python development: keeping documentation accurate as code evolves.

What started as a simple docstring generator has evolved into a documentation validation and coverage platform for Python projects.

PyCodeCommenter -> Creator -> Nabasa Amos (Amos Quety)

## Connect With the Creator

- **Portfolio**: [Projects and work](https://nabasa-amos.netlify.app)
- **GitHub**: [AmosQuety](https://github.com/AmosQuety)
- **LinkedIn**: [Nabasa Amos](https://linkedin.com/in/nabasa-amos)
- **Contact**: amosnabasa4@gmail.com

## License
MIT License - see [LICENSE](LICENSE) file for details.

## Contributing
Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## Show Your Support
If PyCodeCommenter helps your workflow, please star the repo. It helps other developers discover the project.

## Contact
- **Issues**: [GitHub Issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/AmosQuety/PyCodeCommenter/discussions)

