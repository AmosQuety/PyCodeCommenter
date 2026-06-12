# Recipes & Common Workflows

This page provides complete, copy-paste-ready examples for the most common PyCodeCommenter use cases. Every command and code snippet has been verified against the actual source code.

---

## Recipe 1: Pre-commit Hook Setup

Validate docstrings on every commit so documentation issues are caught before they reach the repository.

### Using pre-commit framework

Create or update `.pre-commit-config.yaml` in your project root:

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
        pass_filenames: true
```

> **Note:** The `validate` subcommand accepts a single file path. The `pass_filenames: true` setting tells pre-commit to call the hook once per staged Python file. This is the correct setup because `pycodecommenter validate` does not yet accept directory paths — only file paths are supported.

Install the hook:

```bash
pip install pre-commit
pre-commit install
```

From now on, every `git commit` will run `pycodecommenter validate` on each staged Python file and block the commit if any ERROR-level issues are found.

---

## Recipe 2: The CI Configurator

Run a documentation quality check on every push and pull request. Use the configurator below to generate the exact YAML snippet for your provider and package manager.

<div class="pcc-ci-widget">
  <div class="pcc-ci-controls">
    <label for="ci-provider">Provider:</label>
    <select id="ci-provider">
      <option value="github">GitHub Actions</option>
      <option value="gitlab">GitLab CI</option>
    </select>

    <label for="ci-manager">Package Manager:</label>
    <select id="ci-manager">
      <option value="pip">pip</option>
      <option value="poetry">Poetry</option>
      <option value="uv">uv</option>
    </select>
    
    <label for="ci-level">Enforcement Level:</label>
    <select id="ci-level">
      <option value="block">Block PRs on Error</option>
      <option value="warn">Warn Only (Dry Run)</option>
    </select>
  </div>

  <pre><code id="ci-output" class="language-yaml"># .github/workflows/docs-check.yml
name: Documentation Check
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install PyCodeCommenter
        run: pip install pycodecommenter
      - name: Check for documentation issues
        run: pycodecommenter validate src/</code></pre>
</div>

---

## Recipe 3: Documenting an Existing Codebase Safely

When adding docstrings to a codebase that has none, use this three-step workflow to avoid accidental data loss.

### Step 1 — Preview what will change

```bash
pycodecommenter generate src/api.py --dry-run
```

Read through the diff carefully. The generated docstrings will have placeholder `Returns:` descriptions (`"Description of the return value."`) that you will want to update.

### Step 2 — Back up, then apply

```bash
pycodecommenter generate src/api.py --inplace --backup
```

This creates `src/api.py.bak` before modifying `src/api.py`. If anything goes wrong, restore from the backup:

```bash
cp src/api.py.bak src/api.py
```

### Step 3 — Review and refine

Open `src/api.py` and update the generated docstrings:
- Replace `"Description of the return value."` with a real return description.
- Check that parameter descriptions are accurate (the rule-based descriptions are starting points).
- Verify class docstrings describe the actual purpose of the class.

### Step 4 — Validate the result

```bash
pycodecommenter validate src/api.py
```

Fix any remaining WARNING or INFO issues, then commit.

---

## Recipe 4: Coverage Gating in CI

Fail the CI build if documentation coverage falls below a threshold. The CLI `coverage` subcommand always exits with code 0, so threshold enforcement must be done via the Python API.

Create a script `check_coverage.py`:

```python
# check_coverage.py
import sys
from PyCodeCommenter import CoverageAnalyzer

THRESHOLD = 80.0  # Minimum acceptable coverage percentage

analyzer = CoverageAnalyzer()
project = analyzer.analyze_directory("./src", exclude_patterns=["migrations", "tests"])
project.print_report()

if project.total_coverage < THRESHOLD:
    print(f"\nFAILED: Coverage {project.total_coverage:.1f}% is below threshold {THRESHOLD}%")
    sys.exit(1)

print(f"\nPASSED: Coverage {project.total_coverage:.1f}% meets threshold {THRESHOLD}%")
sys.exit(0)
```

Add to your GitHub Actions workflow:

```yaml
      - name: Check coverage threshold
        run: python check_coverage.py
```

> **Note:** The `coverage.threshold` and `coverage.fail_below` keys in `.pycodecommenter.yaml` are documented in the README but are not yet wired into the runtime. Use the Python API approach above for reliable threshold enforcement.

---

## Recipe 5: Excluding Test Files

When running coverage on a project, you often want to exclude test files and generated code.

**Via the CLI:**

```bash
pycodecommenter coverage . --exclude tests migrations __pycache__ vendor
```

The `--exclude` values are matched as substrings against each file path. A file is skipped if any of the patterns appears anywhere in its path.

**Via the Python API:**

```python
from PyCodeCommenter import CoverageAnalyzer

analyzer = CoverageAnalyzer()
project = analyzer.analyze_directory(
    "./",
    exclude_patterns=["tests", "test_", "migrations", "vendor", "__pycache__", ".git"]
)
project.print_report()
```

> **Default exclusions:** When `exclude_patterns` is `None`, `CoverageAnalyzer.analyze_directory()` uses `['__pycache__', '.git', 'venv', 'tests', 'test_']`. Passing your own list **replaces** this default — it does not extend it.

---

## Recipe 6: Checking a Single Function Programmatically

Use the Python API to check the docstring quality of specific code, without touching a file on disk.

```python
from PyCodeCommenter import PyCodeCommenter

code = """
def send_email(to_address: str, subject: str, body: str) -> bool:
    \"\"\"Send an email message.

    Args:
        to_address (str): Recipient email address.
        subject (str): Subject of the email.

    Returns:
        bool: True if the email was sent successfully.
    \"\"\"
    # body parameter is missing from Args — validator will catch this
    import smtplib
    return True
"""

commenter = PyCodeCommenter().from_string(code)
report = commenter.validate()
report.print_summary()

# Check programmatically
for issue in report.issues:
    print(f"[{issue.severity.value}] {issue.message}")
    if issue.suggestion:
        print(f"  Fix: {issue.suggestion}")
```

Expected output:
```
============================================================
VALIDATION REPORT
============================================================
File: None
Coverage: 100.0%
Total Issues: 1
  - Errors: 1
  - Warnings: 0
  - Info: 0

ISSUES:

[ERROR] code:2:send_email: Parameter 'body' is not documented in docstring
  → Suggestion: Add 'body' to the Args section
```

---

## Recipe 7: Generating and Immediately Validating

Generate docstrings and then run validation in one script — useful for CI pipelines that need to both add docs and verify quality in a single run.

```python
import sys
from PyCodeCommenter import PyCodeCommenter

file_path = "src/api.py"

# Step 1: Load and generate
commenter = PyCodeCommenter().from_file(file_path)
if not commenter.parsed_code:
    print(f"ERROR: Could not parse {file_path}")
    sys.exit(1)

patched_code = commenter.get_patched_code()

# Step 2: Write the patched code back
with open(file_path, "w", encoding="utf-8") as f:
    f.write(patched_code)

# Step 3: Validate the updated file
from PyCodeCommenter import DocstringValidator
validator = DocstringValidator(file_path=file_path)
report = validator.validate_all()
report.print_summary()

if report.stats.errors > 0:
    sys.exit(1)

print(f"Done. Coverage: {report.stats.coverage_percentage:.1f}%")
```

---

## Related

- **[CLI Reference](cli-reference.md)** — all flags and exit codes
- **[Python API](python-api.md)** — full class and method reference
- **[Configuration](configuration.md)** — `.pycodecommenter.yaml` setup
- **[Validation Checks](validation-checks.md)** — what the validator looks for
