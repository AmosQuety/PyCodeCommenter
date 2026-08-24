# Changelog

All notable changes to PyCodeCommenter will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [2.4.0] - 2026-08-24

### Added
- New shared `PyCodeCommenter/param_utils.py` primitive
  (`get_all_parameters`/`exclude_self_cls`), fixing five independent blind
  spots where positional-only params, keyword-only params, `*args`/`**kwargs`,
  and dataclass/self-assigned class attributes were silently invisible to
  both docstring generation and validation — all three sites that inspected
  a function's parameters (the generator's Args-writer, and two validator
  checks) previously rebuilt that list from `func_node.args.args` alone.
- Generator functions (containing a `yield`) now get a `Yields:` section
  instead of an incorrect `Returns: None`.
- `--badge-output PATH` flag on `pycodecommenter coverage` (and the
  underlying `coverage.shields_badge_dict()`), emitting a shields.io
  endpoint-badge JSON file for the coverage percentage.
- CI now runs the full test suite, including `inference.py`'s doctest
  examples, on every push/PR against `main`
  (`.github/workflows/tests.yml`, new; matrix over Python 3.9-3.12).

### Changed
- README repositioned to be explicit that generated prose the tool can't
  extract from the AST is a marked placeholder needing review, not finished
  documentation, and to name related tools (pydoclint, interrogate) instead
  of implying PyCodeCommenter is alone in this space. The Roadmap's
  AI-generation item was replaced with a struck-through line plus a warning
  block spelling out the draft-and-review-only constraint, so it can't be
  misread as an open, unclaimed feature.

### Fixed
- Guessed (as opposed to AST-extracted or preserved) docstring content is now
  marked with `GUESS_MARKER = "TODO(pycodecommenter): describe"` instead of
  being presented as finished prose. This string is already in
  `validator.py`'s placeholder blacklist, so generated output with
  unresolved guesses now fails the tool's own quality check instead of
  silently passing it.
- `_get_class_attributes` now also picks up `self.x = ...` assignments
  anywhere in `__init__`'s body (not just `__init__`'s own parameters) and
  class-level `AnnAssign` fields (covers `@dataclass`-style classes with no
  `__init__` written in source).
- `@classmethod`-decorated functions no longer document `cls` in the
  generated Args section (the generator only excluded `self`; the validator
  already excluded both).
- **Python 3.9 import crash in `config.py`.** A live (non-deferred)
  `Exception | None` default-argument annotation needs Python >=3.10 —
  `type.__or__` for builtin/exception types doesn't exist on 3.9, so
  evaluating it at class-definition time (import time) raised `TypeError:
  unsupported operand type(s) for |: 'type' and 'NoneType'`. Since `cli.py`
  imports `config.py`, this broke collection for the entire test suite on
  3.9. Pre-existing since v2.1.0 (2026-06-10), roughly three months before
  this release — caught by this release's own new CI matrix (see above) on
  its first real run. Fixed with `Optional[Exception]` plus `from
  __future__ import annotations`, matching the guard `inference.py` already
  uses for its own `str | None` usage.

## [2.3.0] - 2026-08-22

Follow-up work from an internal engineering audit (`Future Work/Vulnerabilties.md`),
plus a documentation-fidelity pass (Phase 6) found during pre-release review.

### Breaking Changes
- **Minimum Python version raised from 3.8 to 3.9.** `pyproject.toml`'s
  `requires-python` is now `>=3.9`; the `Programming Language :: Python :: 3.8`
  classifier was removed. This was forced by the new `libcst` dependency (see
  below), whose current release requires Python >=3.9. **Any user still on
  Python 3.8 will no longer be able to install new releases of this package.**

### Added
- **New runtime dependency: `libcst>=1.1`.** `get_patched_code()` (the code
  that inserts/updates generated docstrings) was rewritten to apply edits via
  libcst's concrete syntax tree instead of line-number arithmetic on raw
  source text. This is a hard dependency, not optional — installing
  `pycodecommenter` now also installs `libcst`.
- `generate` and `validate` CLI commands now accept a directory as well as a
  single file, recursively collecting `.py` files (mirroring `coverage`'s
  existing directory support).
- `--fail-below THRESHOLD` flag on the `coverage` CLI command; exits 1 when
  coverage is below the threshold.
- `.pycodecommenter.yaml` config is now actually read by the CLI: its
  top-level `exclude` list defaults `-e/--exclude` on all three subcommands,
  and `coverage.threshold` defaults `--fail-below`. Both remain overridable
  by explicit CLI flags. (Previously `config.py` existed but nothing called it.)
- NumPy-style docstrings (`Parameters`/`Returns`/`Raises` with dash-underlined
  headers) are now parsed as input, alongside Google and Sphinx style.
  Sphinx-style input also gained `:type name: TYPE` support.

### Fixed
- **One-line function/class definitions could corrupt the file when patched.**
  `def foo(): return 1` (body on the same physical line as the `def`) would
  have its generated docstring inserted *before* the `def` line instead of
  inside the function, producing a `SyntaxError`. Every one-liner shape
  reproduced this: `pass`, `return`, multiple `;`-separated statements,
  `async def`, and one-line `class` bodies. Fixed by the libcst rewrite above,
  which converts a one-liner body to a proper indented block before inserting.
  (This is a different, narrower bug than the "multi-line signature
  corruption" originally suspected from the audit — see Notes below.)
- `PyCodeCommenter.validate()` now passes the real file path to the validator
  instead of a hardcoded `None`, so validation report locations show the
  actual file (e.g. `src/api.py:12:my_func`) instead of `code:12:my_func`.
- `PyCodeCommenter.check_coverage()` now uses the real file path instead of
  the leaked `"<string>"` placeholder.
- `docstring_parser.py`: multi-line `Args:` parameter descriptions in an
  *existing* docstring being re-parsed were silently truncated unless the
  continuation line was indented by exactly 8 spaces. Any other indentation
  (including 4 spaces — the same indent this project's own generator uses)
  lost the continuation text on merge. Now any non-blank continuation line is
  recognized regardless of indentation depth.
- `generate`/`validate` directory mode's default exclude list
  (`__pycache__`, `.git`, `.venv`, `venv`, `env`, `.eggs`) missed common
  vendor/build directories and used raw substring matching, causing two real
  problems: `environment_config.py` was silently skipped (`"env"` is a
  substring of `"environment"`), and files inside `.tox/.../site-packages/`
  were *not* skipped — with `generate --inplace`, writing generated
  docstrings into vendored third-party source. Expanded the default list
  (added `.tox`, `.nox`, `__pypackages__`, `site-packages`, `build`, `dist`,
  `.egg-info`, `.mypy_cache`, `.pytest_cache`, `node_modules`) and switched
  to exact-path-component matching. `coverage`'s directory mode had the same
  two problems independently (a separate, duplicated exclude list) and is
  fixed the same way, plus a related bug: passing any custom `--exclude`
  pattern previously replaced its default list entirely rather than adding
  to it, silently losing `.venv`/`.git` protection.
- A parameter's documented type (e.g. `x (int):`) was silently downgraded to
  `x (any):` on regeneration whenever static type inference had nothing to
  work with (no annotation on the parameter) — the type was parsed out of
  the existing docstring but never stored or consulted. A real static
  annotation still always wins; the docstring-parsed type is now used as a
  fallback instead of being discarded.
- An existing NumPy-style docstring was not recognized as such, so its
  entire body was treated as free-text and a fresh, auto-generated
  Google-style `Args:`/`Returns:` section was appended underneath it —
  documenting the same parameter twice, in two styles, in one docstring.
- Generated filler text for dunder methods (e.g. `__init__`) rendered with
  broken spacing — `"Original of the   init  ."` — because
  `name.replace('_', ' ')` turns every underscore into a space, including
  the leading/trailing pair(s) dunder names have.

### Changed
- `ValidationStats.infos` renamed to `.info` (matches the existing `"info"`
  key in JSON/markdown output). `.infos` remains available as a
  backward-compatible property alias.

### Notes
- Two "CRITICAL" bugs originally suspected from the audit — corruption on
  multi-line function signatures, and a line-shift bug when patching multiple
  functions in one file — were investigated and do not reproduce against this
  version or the pre-libcst version; both were verified directly against the
  audit's own examples plus additional stress tests. No code changes were
  made for either.
- A third suspected bug — `ast.walk()` double-counting nested
  functions/classes in `validate_all()`'s stats — also does not reproduce;
  `ast.walk()` visits every node exactly once regardless of nesting depth.
  `validator.py`'s counting logic is unchanged.
- PEP 604 union rendering (`int | str` currently renders as `Union[int, str]`
  in generated docstrings, per `type_analyzer.py`) was identified as a real,
  minor issue but deliberately deferred: fixing it breaks
  `test_type_analyzer.py::test_union_annotation`, which asserts the old
  `Union[...]` output, and no test-file changes were in scope for that part
  of the work.

## [2.2.0] - 2026-07-12

### Added
- **Decorator-aware validation** — `@property` setter and deleter variants no longer produce false-positive
  "missing Returns section" warnings. `@classmethod` (`cls`) and `@staticmethod` were verified already correct.
- **`--output-format json`** flag on both `validate` and `coverage` subcommands. Prints machine-readable
  JSON to stdout; text output is completely unchanged.
- **`ValidationReport.to_dict()`** updated to spec-compliant shape: `stats.total`, `stats.info`,
  `stats.coverage_percentage`; issues now include `line` (integer), `severity` (uppercase), `check`, `message`.
- **`_has_raises_section()` helper** in `validator.py` — recognises `Raises:` (Google), `Raises\n`
  (bare header), and `:raises ` (Sphinx, trailing space prevents false matches).
- **`llms.txt`** file at repo root — AI agent and LLM crawler discovery file.
- **SEO/AEO optimisation** — keyword-rich README, PyPI classifiers/keywords, per-page meta tags on all
  doc pages, JSON-LD `SoftwareApplication` schema on docs homepage.

### Changed
- `test_validation.py` rewritten from script-style to proper pytest (17 tests, all pass).
- `pyproject.toml` keywords expanded to 20 terms; classifiers expanded with `Code Generators`,
  `Libraries :: Python Modules`, `Environment :: Console`, `Operating System :: OS Independent`.
- `mkdocs.yml` enriched with `site_author`, explicit `language: en`, `navigation.indexes`,
  `search.share`, `toc.follow`, and `meta` markdown extension for per-page SEO tags.

## [2.0.0] - 2026-01-25

###  Major Release - Complete Rewrite

#### Added
- **Comprehensive Validation System** - 6 types of documentation checks
- **Coverage Analysis** - Project-wide documentation metrics
- **Modern Type Support** - PEP 604 unions, PEP 585 generics
- **Async Function Support** - Full support for `async def`
- **Multiple Export Formats** - JSON, Markdown, console output
- **Smart Docstring Parsing** - Preserves existing documentation
- **Structured AST Traversal** - NodeVisitor pattern for reliability
- **Professional Reporting** - Actionable error messages with suggestions
- **CI/CD Ready** - Easy integration with pipelines

#### Changed
- Replaced basic type inference with comprehensive `TypeAnalyzer`
- Improved docstring generation with better templates
- Enhanced error handling with proper logging
- Better handling of edge cases and malformed code

#### Fixed
- Duplicate `_infer_type` methods consolidated
- Brittle patching logic made robust
- Import resolution issues
- Unicode/encoding handling

#### Breaking Changes
- Minimum Python version: 3.8+
- Some internal APIs changed (public API remains compatible)

## [1.0.0] - Earlier Version

- Basic docstring generation
- Template-based descriptions
- File and string input support
