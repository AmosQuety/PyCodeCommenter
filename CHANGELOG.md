# Changelog

All notable changes to PyCodeCommenter will be documented in this file.

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
