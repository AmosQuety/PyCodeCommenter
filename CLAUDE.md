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

For the current state of work in progress, decisions already made, and
where to begin, read `Future Work/v2.6.0 — Work Log and Handoff.md` first.

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
3.10–3.13) on every push and pull request against `main`, alongside the
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
  - `function_doc.py` / `doc_styles.py` — a docstring as tagged parts
    (`FunctionDoc`, `ClassDoc`, each part carrying its `Origin`: author,
    fact, weak, guess, ai), and rendering them. New docstrings are Google
    style; an existing NumPy/Sphinx docstring (the parser's `style`) is
    re-rendered in its own style, never converted.
  - `review.py` / `review_cli.py` — the `review` subcommand: find AI
    lines, TODO gaps and repeated comments; apply accept/edit/fill/remove
    decisions; `verify_review` blocks saving unless only docstrings and
    comments changed.
  - `run_report.py` — `GenerationReport`, the counts behind the summary
    `generate` prints (to stderr: stdout carries only generated code).
  - `comment_docs.py` — finds the `#` comment block directly above an
    undocumented function/class and turns it into docstring text (author
    text; the comment is never removed). Skips notes, tool directives,
    commented-out code, and section banners.
  - `code_facts.py` — pure functions that phrase facts read straight off a
    function's AST: the condition guarding each `raise` (`raise_sites`,
    `describe_raise_condition`) and a boolean function's single return
    expression (`describe_bool_return`). Each returns `None` unless the
    statement is exact, and `None` means "keep the guess marker".

  Two invariants hold across generation: author text always wins over
  anything derived (text containing `GUESS_MARKER` counts as the tool's
  own, not the author's), and a TODO may only be removed by stating a fact
  the code contains, never by a plausible guess. `Methods:` is never
  generated, but an author's own `Methods:` section is kept.

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
  `[project.scripts]` in `pyproject.toml`) with four subcommands: `review`
  (see below), `generate`
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

- **`function_doc.py`** — a function docstring as parts (`FunctionDoc`),
  each tagged with its `Origin` (author, fact, weak, guess, ai), plus the
  one renderer. `commenter._build_function_doc` builds it; AI drafting and
  any reporting work on the parts, never on rendered text.
- **`description_provider.py`** — the provider interface. `draft_docstring
  (context, known, slots)` drafts the requested `DraftSlots` and returns a
  `DocstringDraft`; its default falls back to the older
  `draft_function_description` (description paragraph only), so providers
  written against that keep working. `DraftingStopped` ends drafting for
  the run (limit spent, key rejected); any other error skips one function.
  `SwitchOnStop` wraps a provider and asks once for a replacement when it
  stops (the "continue with your own key" prompt).
- **`ai_drafting.py`** — which parts are gaps (`slots_for`: only `GUESS`/
  `WEAK` parts), the settled text sent as context (`known_text`), applying
  a draft (`apply_draft`), and the client-side safety gate every drafted
  value passes (`clean_slot_text`: no triple quotes, backslashes, `TODO`,
  or marker text). Also the prompt/JSON schema/reply parser for direct
  providers — the hosted backend keeps its own copy of the prompt, so keep
  the two in step.
- **`remote_provider.py`** — `RemoteDescriptionProvider`, a stdlib-only
  (`urllib`) client for the separate `pycodecommenter-ai-backend` service's
  `/v2/draft-docstring` (falls back to `/v1` on a 404). Records the
  caller's daily allowance from response headers, waits out a per-minute
  rate limit once, and raises `DraftingStopped` when the allowance or
  shared cap is spent.
- **`direct_providers.py`** — bring-your-own-key providers (Gemini,
  OpenAI, Anthropic, DeepSeek, any OpenAI-compatible API) using each
  vendor's official SDK, installed via optional extras (`[gemini]`,
  `[openai]`, `[anthropic]`, `[ai]`). `PROVIDERS` holds each
  one's key variable and default model. SDKs are imported only when chosen;
  tests inject fake clients, so the suite needs no SDK or network.
- **`ai_setup.py`** — CLI-side setup: provider choice, key from the
  provider's env var or a hidden prompt (never a project file), consent,
  the "AI drafting: <provider>, model <m>" line, and the end-of-run report.
- **`consent.py`** — one-time, versioned consent per destination (`hosted`
  or a provider name) at `~/.pycodecommenter/consent.json`. Bump
  `CONSENT_NOTICE_VERSION` / `DIRECT_CONSENT_NOTICE_VERSION` if what is
  sent, or what the destination does with it, materially changes.
- CLI: `generate --ai-draft` opts in; `--ai-provider`/`--ai-model`/
  `--ai-base-url` choose where; `--accept-ai-drafts` is additionally
  required with `--inplace`; `--yes-send-code-to-ai` (alias
  `--yes-send-code-to-hosted-ai`) skips the consent prompt for CI. Every
  drafted line carries an `(AI-drafted, unreviewed)` marker, which the
  validator reports under its own `ai_draft` category.

### Test layout

Tests live flat at the repo root (not in a `tests/` directory) and map
roughly one file per concern: `test_basic_validation.py`,
`test_validation.py` (largest, the six-check validator matrix),
`test_type_analyzer.py`, `test_coverage.py`, `test_edge_cases.py`,
`test_modern.py` (PEP 604/585 and `async def` support),
`test_backwards_compatibility.py`, `test_integration.py`,
`test_docstring_parser.py`, `test_cli.py` (CLI subcommands, including the
AI-draft flags), `test_consent.py`, and `test_remote_provider.py` (HTTP
client, with the network mocked — no test hits the real backend),
`test_ai_drafting.py` (what is asked for, what is written, the safety
gate, failure handling), `test_direct_providers.py` (bring-your-own-key
providers against fake SDK clients, the limit-reached hand-off, consent
per destination), `test_merge_preservation.py` (regeneration never discards author-written
Raises/Attributes/Methods text), and `test_fact_extraction.py` (raise
conditions, bool/str return inference, plus end-to-end fixtures with exact
TODO counts — update those counts deliberately, never to make a test
pass). `scratch/` holds
ad hoc/exploratory test scripts not part of the maintained suite.

### Versioning

Version is hardcoded in two places and must be kept in sync manually:
`pyproject.toml` (`[project].version`) and `PyCodeCommenter/__init__.py`
(`__version__`).
