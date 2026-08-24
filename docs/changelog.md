# Changelog

All notable changes to PyCodeCommenter are documented here. This page mirrors
the root [`CHANGELOG.md`](https://github.com/AmosQuety/PyCodeCommenter/blob/main/CHANGELOG.md)
in the repository, kept manually in sync — see the note at the bottom of this
page.

---

## v2.4.0

*Released: 2026-08-24*

### Added

- **Shared parameter-extraction primitive** (`param_utils.get_all_parameters`/`exclude_self_cls`) — fixes five independent blind spots where positional-only params, keyword-only params, `*args`/`**kwargs`, and dataclass/self-assigned class attributes were silently invisible to both docstring generation and validation. All three sites that inspected a function's parameters (the generator's Args-writer, and two validator checks) previously rebuilt that list from `func_node.args.args` alone.
- Generator functions (containing a `yield`) now get a `Yields:` section instead of an incorrect `Returns: None`.
- **`--badge-output PATH`** flag on `pycodecommenter coverage` (and the underlying `coverage.shields_badge_dict()`), emitting a [shields.io endpoint-badge](https://shields.io/badges/endpoint-badge) JSON file for the coverage percentage.
- **CI now runs the full test suite** — including `inference.py`'s doctest examples — on every push/PR against `main`, across Python 3.9-3.12. There was previously no CI workflow that ran tests at all.

### Changed

- README repositioned to be explicit that generated prose the tool can't extract from the AST is a marked placeholder needing review, not finished documentation, and to name related tools (pydoclint, interrogate) instead of implying PyCodeCommenter is alone in this space. The Roadmap's AI-generation item was replaced with a struck-through line plus a warning block spelling out the draft-and-review-only constraint.

### Fixed

- Guessed (as opposed to AST-extracted or preserved) docstring content is now marked with `GUESS_MARKER = "TODO(pycodecommenter): describe"` instead of being presented as finished prose. This string is already in `validator.py`'s placeholder blacklist, so generated output with unresolved guesses now fails the tool's own quality check instead of silently passing it.
- `_get_class_attributes` now also picks up `self.x = ...` assignments anywhere in `__init__`'s body (not just `__init__`'s own parameters) and class-level `AnnAssign` fields (covers `@dataclass`-style classes with no `__init__` written in source).
- `@classmethod`-decorated functions no longer document `cls` in the generated Args section (the generator only excluded `self`; the validator already excluded both).

---

## v2.3.0

*Released: 2026-08-22*

### Breaking Changes

- **Minimum Python version raised from 3.8 to 3.9.** Forced by the new `libcst` dependency (see below), whose current release requires Python ≥3.9.

### Added

- **New runtime dependency: `libcst>=1.1`.** `get_patched_code()` now applies edits via libcst's concrete syntax tree instead of line-number arithmetic on raw source text.
- `generate` and `validate` CLI commands now accept a directory as well as a single file, recursively collecting `.py` files (mirroring `coverage`'s existing directory support).
- `--fail-below THRESHOLD` flag on the `coverage` CLI command; exits 1 when coverage is below the threshold.
- `.pycodecommenter.yaml` config is now actually read by the CLI: its top-level `exclude` list defaults `-e/--exclude` on all three subcommands, and `coverage.threshold` defaults `--fail-below`. Both remain overridable by explicit CLI flags.
- NumPy-style docstrings (`Parameters`/`Returns`/`Raises` with dash-underlined headers) are now parsed as input, alongside Google and Sphinx style. Sphinx-style input also gained `:type name: TYPE` support.

### Fixed

- **One-line function/class definitions could corrupt the file when patched.** `def foo(): return 1` (body on the same physical line as the `def`) would have its generated docstring inserted *before* the `def` line instead of inside the function, producing a `SyntaxError`. Fixed by the libcst rewrite above, which converts a one-liner body to a proper indented block before inserting.
- `PyCodeCommenter.validate()` and `check_coverage()` now pass/use the real file path instead of a hardcoded placeholder, so report locations show the actual file.
- Multi-line `Args:` parameter descriptions in an *existing* docstring being re-parsed were silently truncated unless the continuation line was indented by exactly 8 spaces. Now any non-blank continuation line is recognized regardless of indentation depth.
- `generate`/`validate`/`coverage` directory mode's default exclude list missed common vendor/build directories and used raw substring matching (e.g. `environment_config.py` was silently skipped, `"env"` being a substring of `"environment"`; files inside `.tox/.../site-packages/` were *not* skipped, risking `generate --inplace` writing into vendored third-party source). Expanded the list and switched to exact-path-component matching; a custom `--exclude` pattern now adds to the defaults instead of replacing them.
- A parameter's documented type was silently downgraded to `(any)` on regeneration whenever static type inference had nothing to work with — the docstring-parsed type is now used as a fallback instead of being discarded.
- An existing NumPy-style docstring was not recognized as such, so a fresh Google-style `Args:`/`Returns:` section was appended underneath it, documenting the same parameter twice.
- Generated filler text for dunder methods (e.g. `__init__`) rendered with broken spacing (`"Original of the   init  ."`); fixed by a dunder-aware humanizer.

### Changed

- `ValidationStats.infos` renamed to `.info` (matches the existing `"info"` key in JSON/markdown output); `.infos` remains available as a backward-compatible alias.

---

## v2.2.0

*Released: 2026-07-12*

### Added

- **Decorator-aware validation** — `@property` setter and deleter variants no longer produce false-positive "missing Returns section" warnings.
- **`--output-format json`** flag on both `validate` and `coverage` subcommands.
- **`_has_raises_section()` helper** in `validator.py` — recognises `Raises:` (Google), a bare `Raises` header, and `:raises ` (Sphinx).
- **SEO/AEO optimisation** — `llms.txt` discovery file, per-page meta tags, JSON-LD schema on the docs homepage.

### Changed

- `ValidationReport.to_dict()` updated to a spec-compliant shape (`stats.total`, `stats.info`, `stats.coverage_percentage`; issues include `line`, `severity`, `check`, `message`).

---

## v2.1.0

### Added

- **Rule-based parameter inference** (`inference.py`) — the `infer_description` function uses a priority chain (name patterns → type hints → default values → generic fallback) to produce concise, meaningful descriptions without any external calls.
- **Config loader** (`config.py`) — `load_config()` searches upward from the current directory for `.pycodecommenter.yaml` and parses it with `ruamel.yaml`. `ConfigError` is raised on parse failure; a missing file returns an empty dict.
- **`--dry-run` flag** for `pycodecommenter generate` — prints a unified diff to stdout and exits with code 1 if changes exist, code 0 if none.
- **`--backup` flag** for `pycodecommenter generate --inplace` — copies the original file to `<file>.bak` before modifying it.
- **`--output` / `-o` flag** for `pycodecommenter generate` — writes the result to a specified output file instead of stdout.

---

## v2.0.0 — Complete Rewrite

*Released: 2026-01-25*

### Added

- **Comprehensive validation system** — six categories of documentation checks: signature matching, type consistency, exception documentation, return documentation, format compliance, and content quality.
- **Coverage analysis** — `CoverageAnalyzer`, `FileCoverage`, and `ProjectCoverage` classes for per-file and project-wide documentation metrics.
- **Modern type support** — `TypeAnalyzer` handles PEP 604 union types (`int | str`), PEP 585 generics (`list[int]`), subscripted types (`Dict[str, Any]`), and attribute types (`typing.Optional`).
- **Async function support** — `async def` functions are fully processed by both the generator and the validator.
- **Multiple export formats** — `ValidationReport` can export to console (`print_summary()`), JSON (`to_dict()`), and Markdown (`to_markdown()`).
- **Smart docstring merging** — `DocstringParser` reads existing Google-style and Sphinx-style docstrings; existing text is preserved when regenerating.
- **Structured AST traversal** — `DocstringVisitor` (a `NodeVisitor` subclass) replaces the previous ad-hoc walk, producing reliable results on nested classes and functions.
- **Severity enum** — `Severity.ERROR`, `Severity.WARNING`, and `Severity.INFO` replace plain strings.
- **`ValidationIssue` dataclass** — structured issue objects with `severity`, `category`, `location`, `message`, and `suggestion` fields.
- **`ValidationStats` dataclass** — aggregated counters with a `coverage_percentage` property.
- **CI/CD-ready exit codes** — `validate` exits 1 on any ERROR; `generate --dry-run` exits 1 when changes are needed.

### Changed

- Basic type inference replaced by comprehensive `TypeAnalyzer` class.
- Docstring generation templates improved with a 60+ verb pattern dictionary (`templates.py`).
- Error handling unified under `logging` module throughout all modules.
- All file reads use `encoding='utf-8'` explicitly.

### Fixed

- Duplicate `_infer_type` methods consolidated into `TypeAnalyzer`.
- Brittle line-based patching logic replaced with AST-aware position tracking.
- Import resolution errors when running modules directly (try/except import fallback pattern).
- Unicode/encoding issues when reading source files.

### Breaking Changes

- Minimum Python version raised to 3.8.
- Some internal private APIs changed; the public API (`PyCodeCommenter`, `generate_docstrings`, `get_patched_code`, `validate`, `check_coverage`) is backward compatible.

---

## v1.0.0 — Initial Release

*Earlier version*

### Added

- Basic docstring generation for functions and classes.
- Template-based descriptions using a verb-to-template dictionary.
- File input (`from_file`) and string input (`from_string`).
- Simple `generate` CLI subcommand.

---

## Related

- **[Getting Started](getting-started.md)** — upgrade path and first steps
- **[FAQ](faq.md)** — version-related questions

---

<!--
Maintenance note: this page is a hand-adapted copy of the root CHANGELOG.md,
not a generated one -- the two must be updated together, or this page drifts
stale again (as it did across v2.2.0/v2.3.0 before this pass). mkdocs.yml
does not currently enable `pymdownx.snippets`; if it were added to
markdown_extensions, this page could use a `--8<--` snippet include to pull
CHANGELOG.md's content in directly instead of duplicating it by hand, which
would remove the sync burden entirely. Not implemented here -- flagged as a
follow-up idea, out of scope for this pass.
-->
