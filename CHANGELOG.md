# Changelog

All notable changes to PyCodeCommenter will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
