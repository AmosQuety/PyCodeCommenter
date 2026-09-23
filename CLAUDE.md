# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PyCodeCommenter is a deterministic, AST-based Python docstring generator and
validator (published to PyPI as `pycodecommenter`). It generates Google-style
docstrings from a function's actual signature, validates existing docstrings
against real code (catching drift), and measures documentation coverage. By
default there are no network calls and no AI/LLM dependency — code analysis
is done with the stdlib `ast` module. The one exception is the explicit
opt-in `generate --ai-draft` path (see "Opt-in AI drafting" below), which
sends function source to a separate hosted backend. Runtime dependencies:
`ruamel.yaml` (for `.pycodecommenter.yaml` config loading) and `libcst` (for
source-preserving docstring patching in `commenter.py`'s
`get_patched_code()`).

Note: the repo root (this directory) contains the installable package
directory `PyCodeCommenter/`, one level deep (not nested further). All
commands below assume you're in this top-level directory unless noted.

## Commands

Install for development:
```bash
pip install -e ".[dev]"
```

The local dev environment is the repo's `.venv/` — there is no bare `python`
on PATH, so either activate it (`source .venv/bin/activate`) or invoke
`.venv/bin/python -m pytest .` etc. directly.

Run the full test suite:
```bash
pytest .
```
(The explicit `.` matters: `pyproject.toml`'s `[tool.pytest.ini_options]`
scopes `--doctest-modules` to the `PyCodeCommenter` package via a positional
path in `addopts`, and pytest treats any positional path — from `addopts` or
the command line — as the sole collection root when no other path is given.
A bare `pytest` therefore silently collects only that package's 2 doctest
items and skips all the `test_*.py` files at the repo root; `pytest .` adds
the repo root back as a second collection root, which is why CI invokes
`pytest .` too.)

Run a single test file / test:
```bash
pytest test_validation.py
pytest test_validation.py::test_name -v
```

There is no separate pytest config file (no `pytest.ini`/`setup.cfg`/
`tox.ini`) and `conftest.py` is empty, but `pyproject.toml` does carry a
`[tool.pytest.ini_options]` section (the `addopts` behind the `pytest .`
note above) — that's the only pytest configuration in the repo.
`.github/workflows/tests.yml` runs the suite (`pytest .`, matrix over Python
3.9–3.12) on every push and pull request against `main`, alongside the
pre-existing `docs.yml` (MkDocs) and `publish.yml` (PyPI trusted publishing
on release) — so CI, not just a local run, is a test signal now.

Formatting / linting (per CONTRIBUTING.md, use before submitting changes):
```bash
black .
flake8
```

Run the CLI locally without installing:
```bash
python -m PyCodeCommenter.cli generate <file.py> --dry-run
# or, if installed (pip install -e .):
pycodecommenter generate <file.py> --dry-run
pycodecommenter validate <file.py> --output-format json
pycodecommenter coverage <path> -e "*/tests/*"
```

Build the docs site locally:
```bash
pip install mkdocs mkdocs-material
mkdocs build --strict --site-dir _site
```

## Architecture

The package (`PyCodeCommenter/`) is organized as a pipeline of focused
AST-driven modules, all importable from the top-level package (`__init__.py`
re-exports the public API):

- **`commenter.py`** — `PyCodeCommenter`, the main entry class. Loads code
  from a file or string (`from_file`/`from_string`), parses it with `ast`,
  walks the tree via an internal `DocstringVisitor`, and produces patched
  source with `get_patched_code()`. It merges rather than overwrites: existing
  summary/param/return text is preserved, only missing sections are filled
  in. Docstring generation composes several helper modules:
  - `templates.py` — verb→template description map. Currently unused by the
    generator (which uses `humanize_identifier` instead); retained as the
    pattern the `v3.0.0` multi-style output work is planned to extend, per
    `Future Work/v3.0.0...txt`.
  - `inference.py` — infers human-readable parameter descriptions from name,
    type hint, and default value.
  - `type_analyzer.py` — `TypeAnalyzer`, infers types from annotations and
    AST shape, including PEP 604 unions (`int | str`) and PEP 585 generics
    (`list[int]`).
  - `docstring_parser.py` — `DocstringParser`, parses existing docstrings
    (Google-style and Sphinx-style `:param:`/`:returns:`/`:raises:` as input)
    into a structured form so they can be diffed against the real signature.
  - `param_utils.py` — the single shared primitive (used by both
    `commenter.py` and `validator.py`) for extracting a function's full
    parameter list, including positional-only, keyword-only, `*args`, and
    `**kwargs`, plus scope-bounded AST walkers (`walk_own_scope` etc.) so a
    `return`/`yield`/`raise` in a nested `def` isn't attributed to the
    outer function. Use it rather than reading `func_node.args.args`.

- **`validator.py`** — `DocstringValidator` walks the AST independently of
  the generator and checks documented functions against six rules: signature
  match (params in `Args:` vs actual params), type consistency, exception
  documentation (`raise` requires `Raises:`), return documentation (`return
  <value>` requires `Returns:`), format compliance, and content quality
  (placeholder/duplicate text). It is decorator-aware: `@property`
  setters/deleters skip the return check, `@classmethod` excludes `cls`,
  `@staticmethod` validates all params including the first. Produces a
  `ValidationReport` (`ValidationIssue` list + `ValidationStats`) with
  `Severity.ERROR/WARNING/INFO`; `validate` CLI/API exits/reports non-zero
  when ERROR-level issues exist, making it CI-blocking.

- **`coverage.py`** — `CoverageAnalyzer` walks a file or directory tree and
  computes `FileCoverage`/`ProjectCoverage`: a function/class counts as
  "documented" if its first body statement is a non-empty string literal.
  No relation to the validator's correctness checks — this is purely a
  presence metric.

- **`config.py`** — `load_config()` searches upward from a start path (or
  cwd) for `.pycodecommenter.yaml`, parses it with `ruamel.yaml`, and returns
  a dict; returns `{}` if none is found, raises `ConfigError` if the file
  exists but fails to parse.

- **`cli.py`** — argparse-based CLI (`pycodecommenter` entry point, see
  `[project.scripts]` in `pyproject.toml`) with three subcommands: `generate`
  (supports `--inplace`, `-o/--output`, `--output-dir`, `--dry-run`,
  `--backup`, `--exclude`, `--include-module-docstrings`, and the AI flags
  below), `validate`, and `coverage` (both supporting `--output-format
  text|json`; `coverage` also has `--fail-below` and `--badge-output`). This is a
  thin orchestration layer over `commenter.py`/`validator.py`/`coverage.py` —
  business logic belongs in those modules, not here.

Each core module has a corresponding `try/except (ImportError, ValueError):`
relative-then-absolute import fallback (e.g. in `commenter.py`, `validator.py`)
so the modules remain runnable both as part of the installed package and as
standalone scripts — preserve this pattern if you add new intra-package
imports.

### Opt-in AI drafting

Entirely inert unless the caller opts in; the deterministic path above is
the tool's default behavior.

- **`description_provider.py`** — the pluggable `DescriptionProvider`
  interface plus the `FunctionContext`/`ParameterFact` value objects
  (AST-extracted facts handed to a provider). The default
  `NullDescriptionProvider` always declines. A provider is only consulted
  when a caller passes `PyCodeCommenter(description_provider=...)`.
- **`remote_provider.py`** — `RemoteDescriptionProvider`, a stdlib-only
  (`urllib`) HTTP client for the separate `pycodecommenter-ai-backend`
  service (default `DEFAULT_BACKEND_URL`, overridable via the
  `PYCODECOMMENTER_AI_BACKEND_URL` env var). It holds no Gemini/model
  knowledge or API keys — that all lives in the backend repo. It fails
  closed: any error, timeout, 429, or malformed response yields `None`,
  never a raised exception.
- **`consent.py`** — one-time, versioned consent stored per user at
  `~/.pycodecommenter/consent.json`. Bump `CONSENT_NOTICE_VERSION` if what
  is sent to or done by the backend materially changes, so users are
  re-prompted.
- CLI: `generate --ai-draft` opts in; `--accept-ai-drafts` is additionally
  required with `--inplace`; `--yes-send-code-to-hosted-ai` skips the
  interactive consent prompt (CI use). Every AI-drafted description carries
  an `(AI-drafted, unreviewed)` marker, which the validator reports under
  its own `ai_draft` category — never counted as properly documented.

### Test layout

Tests live flat at the repo root (not in a `tests/` directory) and map
roughly one file per concern: `test_basic_validation.py`,
`test_validation.py` (largest, the six-check validator matrix),
`test_type_analyzer.py`, `test_coverage.py`, `test_edge_cases.py`,
`test_modern.py` (PEP 604/585 and `async def` support),
`test_backwards_compatibility.py`, `test_integration.py`,
`test_docstring_parser.py`, `test_cli.py` (CLI subcommands, including the
AI-draft flags), `test_consent.py`, and `test_remote_provider.py` (HTTP
client, with the network mocked — no test hits the real backend). `scratch/` holds
ad hoc/exploratory test scripts not part of the maintained suite.

### Versioning

Version is hardcoded in two places and must be kept in sync manually:
`pyproject.toml` (`[project].version`) and `PyCodeCommenter/__init__.py`
(`__version__`).
