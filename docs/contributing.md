# Contributing to PyCodeCommenter

Thank you for considering a contribution to PyCodeCommenter. Every bug report, documentation improvement, and code contribution makes the tool better for everyone.

---

## Ways to Contribute

### Reporting Bugs

Found something broken? Before opening an issue:

1. Check [existing issues](https://github.com/AmosQuety/PyCodeCommenter/issues) to avoid duplicates.
2. If it hasn't been reported, [open a new issue](https://github.com/AmosQuety/PyCodeCommenter/issues/new) with:
   - A clear title describing the problem
   - The Python version and PyCodeCommenter version you are running
   - A minimal code snippet that reproduces the bug
   - The actual output and the expected output

### Proposing Enhancements

Have an idea for a new feature?

1. Open an issue to discuss the idea **before** starting work. This avoids duplicated effort and helps align on design.
2. Explain what the feature would do and why it is useful.
3. If the discussion is positive, you are welcome to open a pull request.

### Improving Documentation

Documentation fixes are always welcome — no discussion needed for small corrections. For larger documentation additions (new pages, new sections), open an issue first.

---

## Pull Request Workflow

1. **Fork** the repository and create a branch from `main`:

   ```bash
   git checkout -b fix/my-bug-description
   ```

2. **Make your changes.** See the code style guidelines below.

3. **Add tests** if you are adding new functionality. The test suite uses `pytest`:

   ```bash
   pytest .
   ```

   (The explicit `.` matters — see `CLAUDE.md`'s "Run the full test suite" note for why a bare `pytest` silently skips most of the suite in this repo.)

4. **Ensure all tests pass** before opening a pull request.

5. **Update documentation** if your change affects the public API, CLI flags, or behaviour visible to users. The docs live in the `docs/` directory.

6. **Open a pull request** against `main` with a clear description of:
   - What the change does
   - Why it is needed
   - Any relevant issue numbers (e.g. `Fixes #42`)

---

## Code Style

| Tool | Usage |
|------|-------|
| [black](https://github.com/psf/black) | Code formatting — run `black .` before committing |
| Google-style docstrings | All new functions and classes must have docstrings |
| Python 3.9+ | Do not use syntax or stdlib features introduced after 3.9 |

Run PyCodeCommenter itself on any new code you write:

```bash
pycodecommenter validate <your_file.py>
```

Validation must pass (no ERRORs) before the pull request will be merged.

---

## Development Setup

```bash
# Clone your fork
git clone https://github.com/<your-username>/PyCodeCommenter.git
cd PyCodeCommenter

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the test suite (the explicit "." matters -- see CLAUDE.md)
pytest .

# Run validation on the package itself
pycodecommenter validate PyCodeCommenter/
```

Dev dependencies (installed by `pip install -e ".[dev]"`):
- `pytest >= 7.0`
- `pytest-cov >= 4.0`
- `black >= 23.0`
- `flake8 >= 6.0`

---

## Need Help?

Feel free to [open a discussion](https://github.com/AmosQuety/PyCodeCommenter/discussions) or [open an issue](https://github.com/AmosQuety/PyCodeCommenter/issues) if you have any questions. No question is too small.

---

## Related

- **[Getting Started](getting-started.md)** — learn how the tool works before contributing
- **[Python API](python-api.md)** — understand the internal classes
- **[Changelog](changelog.md)** — see what has changed across versions
