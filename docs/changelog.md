# Changelog

All notable changes to PyCodeCommenter are documented here.

---

## v2.1.0

*Current release*

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
