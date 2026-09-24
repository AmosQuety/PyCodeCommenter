"""
CLI entry point for PyCodeCommenter.
"""

import sys
import json
import argparse
import os
import difflib
import shutil
from pathlib import Path
from . import __version__
from .commenter import PyCodeCommenter
from .validator import DocstringValidator
from .coverage import CoverageAnalyzer, shields_badge_dict
from .config import load_config, ConfigError
from .ai_setup import (
    AI_PROVIDER_CHOICES,
    AISetupError,
    build_ai_provider,
    report_ai_outcome,
    status,
)
from .run_report import GenerationReport
from .direct_providers import PROVIDERS
from .remote_provider import DEFAULT_BACKEND_URL

# Directories that are never treated as source when recursively collecting
# .py files for `generate`/`validate` on a directory target. These are all
# directories that can hold complete vendored/installed dependency trees or
# build output - the risk isn't wasted effort, it's `--inplace` writing
# generated docstrings into code the user doesn't own or care about.
DEFAULT_DIRECTORY_EXCLUDES = [
    "__pycache__",  # bytecode cache
    ".git",  # VCS metadata
    ".venv",
    "venv",
    "env",  # common virtualenv directory names
    ".tox",  # tox per-environment venvs (full vendored deps)
    ".nox",  # nox per-session venvs, same risk as .tox
    "__pypackages__",  # PEP 582 local package installs
    "site-packages",  # installed-package dir name, catches venvs with a
    # naming scheme not covered above
    "build",  # setuptools/build-backend output
    "dist",  # sdist/wheel output
    ".eggs",  # setuptools .eggs cache
    ".egg-info",  # <package-name>.egg-info metadata dirs
    ".mypy_cache",  # mypy cache
    ".pytest_cache",  # pytest cache
    "node_modules",  # JS/npm dependencies (hybrid-language repos)
]


def _path_is_excluded(py_file, patterns):
    """A path is excluded if one of its directory/file name components
    exactly equals an exclude pattern, or - for a dot-prefixed pattern like
    '.egg-info' - a component ends with it (covers the <name>.egg-info
    convention, where <name> varies per package).

    Exact-component matching, rather than a raw substring check against the
    whole path, avoids excluding legitimate files that merely contain a
    pattern as a substring - e.g. rebuild_index.py must not be skipped just
    because it contains "build", and environment_config.py must not be
    skipped just because it contains "env".
    """
    parts = py_file.parts
    for pattern in patterns:
        for part in parts:
            if part == pattern:
                return True
            if pattern.startswith(".") and part.endswith(pattern):
                return True
    return False


def _collect_py_files(directory, exclude_patterns=None):
    """Recursively collect .py files under directory, skipping any path
    matched by _path_is_excluded() against DEFAULT_DIRECTORY_EXCLUDES plus
    exclude_patterns.
    """
    patterns = list(DEFAULT_DIRECTORY_EXCLUDES) + list(exclude_patterns or [])
    return [
        str(py_file)
        for py_file in sorted(Path(directory).rglob("*.py"))
        if not _path_is_excluded(py_file, patterns)
    ]


def _generate(args, description_provider, run_report):
    """Runs the generate command for a file or directory target.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        description_provider (Optional[DescriptionProvider]): The AI
            provider for --ai-draft, or ``None``.
        run_report (GenerationReport): Accumulates each file's counts for
            the end-of-run summary.
    """
    if os.path.isdir(args.file):
        if args.output:
            print("Error: --output cannot be used with a directory target.")
            sys.exit(1)
        if args.output_dir and args.inplace:
            print("Error: --output-dir cannot be combined with --inplace.")
            sys.exit(1)

        targets = _collect_py_files(args.file, args.exclude)
        if not targets:
            print(f"No Python files found in {args.file}")
            sys.exit(0)

        if args.backup and not args.inplace:
            print("Warning: --backup has no effect without --inplace")

        any_changed = False
        any_failed = False
        written_count = 0
        for target in targets:
            commenter = PyCodeCommenter(
                description_provider=description_provider,
                include_module_docstrings=args.include_module_docstrings,
            ).from_file(target)
            if not commenter.parsed_code:
                print(f"[FAIL] Could not parse {target}")
                any_failed = True
                continue

            patched_code = commenter.get_patched_code()
            run_report.merge(commenter.report)

            if args.output_dir:
                # Mirror this file's relative path under --output-dir,
                # same as document_folder.py-style external scripts
                # had to hand-roll to get a full, on-disk documented
                # copy without touching the originals or reconstructing
                # a tree from a diff by hand.
                rel_path = os.path.relpath(target, args.file)
                out_path = Path(args.output_dir) / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                # newline="": patched_code may contain a CRLF file's
                # real "\r\n" (get_patched_code() restores the source's
                # own convention), which must be written verbatim.
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    f.write(patched_code)
                print(f"[OK] {target} -> {out_path}")
                written_count += 1
                continue

            if args.dry_run:
                with open(target, "r", encoding="utf-8") as f:
                    original_code = f.read()
                diff_lines = list(
                    difflib.unified_diff(
                        original_code.splitlines(),
                        patched_code.splitlines(),
                        fromfile=target,
                        tofile=target,
                        lineterm="",
                    )
                )
                if diff_lines:
                    print("\n".join(diff_lines))
                    any_changed = True
                continue

            if args.inplace:
                # newline="" on both sides: patched_code may contain a
                # CRLF file's real "\r\n" (get_patched_code() restores
                # the source's own convention), so the comparison and
                # the write must see it without any translation, or a
                # CRLF file would look "changed" on every run even when
                # nothing did, and (on Windows) risk double-translating
                # to "\r\r\n" on write.
                with open(target, "r", encoding="utf-8", newline="") as f:
                    original_code = f.read()
                if patched_code != original_code:
                    if args.backup:
                        shutil.copy2(target, target + ".bak")
                    with open(target, "w", encoding="utf-8", newline="") as f:
                        f.write(patched_code)
                    print(f"Successfully patched {target}")
                    any_changed = True
            else:
                print(f"# File: {target}")
                print(patched_code)

        if args.output_dir:
            print(
                f"Wrote {written_count}/{len(targets)} file(s) to " f"{args.output_dir}"
            )
            sys.exit(1 if any_failed else 0)
        if args.dry_run:
            if not any_changed:
                print("No changes detected.")
            sys.exit(1 if any_changed else 0)
        if any_failed:
            sys.exit(1)
        return

    if args.output_dir:
        print("Error: --output-dir cannot be used with a single-file target.")
        sys.exit(1)

    commenter = PyCodeCommenter(
        description_provider=description_provider,
        include_module_docstrings=args.include_module_docstrings,
    ).from_file(args.file)
    if not commenter.parsed_code:
        print(f"Error: Could not parse {args.file}")
        sys.exit(1)

    patched_code = commenter.get_patched_code()
    run_report.merge(commenter.report)

    if args.backup and not args.inplace:
        print("Warning: --backup has no effect without --inplace")

    # Dry-run: show diff and exit without writing
    if args.dry_run:
        with open(args.file, "r", encoding="utf-8") as f:
            original_code = f.read()
        diff_lines = list(
            difflib.unified_diff(
                original_code.splitlines(),
                patched_code.splitlines(),
                fromfile=args.file,
                tofile=args.file,
                lineterm="",
            )
        )
        if diff_lines:
            print("\n".join(diff_lines))
            # Exit with code 1 to indicate there are changes
            sys.exit(1)
        else:
            print("No changes detected.")
            sys.exit(0)

    if args.inplace:
        # Backup if requested
        if args.backup:
            shutil.copy2(args.file, args.file + ".bak")
        # newline="": patched_code may contain a CRLF file's real
        # "\r\n" (get_patched_code() restores the source's own
        # convention), which must be written verbatim, not
        # double-translated to "\r\r\n" on Windows.
        with open(args.file, "w", encoding="utf-8", newline="") as f:
            f.write(patched_code)
        print(f"Successfully patched {args.file}")
    elif args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(patched_code)
        print(f"Successfully wrote patched code to {args.output}")
    else:
        print(patched_code)


def main():
    try:
        config = load_config()
    except ConfigError as e:
        print(f"Warning: {e}", file=sys.stderr)
        config = {}

    config_exclude = config.get("exclude")
    config_fail_below = (config.get("coverage") or {}).get("threshold")

    parser = argparse.ArgumentParser(
        description=(
            "PyCodeCommenter CLI - Automatic docstring generation and validation."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command
    generate_parser = subparsers.add_parser(
        "generate", help="Generate docstrings for a file or directory"
    )
    generate_parser.add_argument("file", help="Python file or directory to process")
    generate_parser.add_argument(
        "-i", "--inplace", action="store_true", help="Modify file(s) in place"
    )
    generate_parser.add_argument(
        "-o", "--output", help="Output file path (single-file targets only)"
    )
    generate_parser.add_argument(
        "--output-dir",
        help=(
            "Write a fully-documented copy of a directory target's tree to "
            "PATH, mirroring each file's relative path, leaving the "
            "originals untouched (directory targets only). Mutually "
            "exclusive with --inplace."
        ),
    )
    generate_parser.add_argument(
        "--dry-run", action="store_true", help="Show diff without writing any files"
    )
    generate_parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a .bak backup before inplace modification",
    )
    generate_parser.add_argument(
        "-e",
        "--exclude",
        nargs="*",
        default=config_exclude,
        help="Patterns to exclude (directory targets only)",
    )
    generate_parser.add_argument(
        "--include-module-docstrings",
        action="store_true",
        help=(
            "Also generate a module-level docstring for a file that has "
            "none at all. Off by default: unlike a missing function/class "
            "docstring, this touches the output of nearly every file that "
            "lacks a module docstring, not just ones that need it most."
        ),
    )
    generate_parser.add_argument(
        "--ai-draft",
        action="store_true",
        help=(
            "Opt in to AI drafting for the parts of a docstring the code "
            "can't state: summaries, and parameter, return and exception "
            "descriptions that would otherwise be TODO markers or say "
            "nothing beyond the type. Uses PyCodeCommenter's free hosted "
            "service (daily limit) unless --ai-provider names your own. "
            "Every drafted line carries a permanent '(AI-drafted, "
            "unreviewed)' marker. Asks once for consent before sending "
            "code anywhere (see --yes-send-code-to-ai for CI). With "
            "--inplace, also requires --accept-ai-drafts; --dry-run and "
            "--output-dir work alone, since those are already review-first."
        ),
    )
    generate_parser.add_argument(
        "--ai-provider",
        choices=AI_PROVIDER_CHOICES,
        default="hosted",
        help=(
            "Where --ai-draft sends code: 'hosted' (default, free, daily "
            "limit, no key needed) or your own key with "
            + ", ".join(
                f"{name} (reads {spec.env_var})" for name, spec in PROVIDERS.items()
            )
            + ". If the variable isn't set you're asked for the key "
            '(hidden). Extras: pip install "pycodecommenter[gemini]", '
            "[openai] (also deepseek, openai-compatible) or [anthropic]."
        ),
    )
    generate_parser.add_argument(
        "--ai-model",
        metavar="MODEL",
        help=(
            "The model to use with --ai-provider; you can always choose your "
            "own. Defaults: "
            + ", ".join(
                f"{name}={spec.default_model}"
                for name, spec in PROVIDERS.items()
                if spec.default_model
            )
            + ". Required for openai-compatible."
        ),
    )
    generate_parser.add_argument(
        "--ai-base-url",
        metavar="URL",
        help=(
            "API endpoint for --ai-provider openai-compatible (e.g. a Mistral, "
            "Groq or local Ollama server)."
        ),
    )
    generate_parser.add_argument(
        "--accept-ai-drafts",
        action="store_true",
        help=(
            "Required alongside --ai-draft when also using --inplace -- an "
            "explicit, separate acknowledgment that unreviewed AI-drafted "
            "text is being written straight to your source files."
        ),
    )
    generate_parser.add_argument(
        "--yes-send-code-to-ai",
        "--yes-send-code-to-hosted-ai",
        dest="yes_send_code_to_ai",
        action="store_true",
        help=(
            "Skip the interactive consent prompt for --ai-draft and "
            "record consent for the chosen provider automatically -- for "
            "non-interactive/CI use. Has no effect if consent is already "
            "on file."
        ),
    )
    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate docstrings for a file or directory"
    )
    validate_parser.add_argument("file", help="Python file or directory to validate")
    validate_parser.add_argument(
        "-e",
        "--exclude",
        nargs="*",
        default=config_exclude,
        help="Patterns to exclude (directory targets only)",
    )
    validate_parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: 'text' (default) or 'json'",
    )

    # Coverage command
    coverage_parser = subparsers.add_parser(
        "coverage", help="Analyze documentation coverage"
    )
    coverage_parser.add_argument("path", help="Directory or file to analyze")
    coverage_parser.add_argument(
        "-e", "--exclude", nargs="*", default=config_exclude, help="Patterns to exclude"
    )
    coverage_parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: 'text' (default) or 'json'",
    )
    coverage_parser.add_argument(
        "--fail-below",
        type=float,
        default=config_fail_below,
        metavar="THRESHOLD",
        help="Exit with code 1 if coverage is below THRESHOLD "
        "(default: coverage.threshold from .pycodecommenter.yaml, if set)",
    )
    coverage_parser.add_argument(
        "--badge-output",
        metavar="PATH",
        help=(
            "Write a shields.io endpoint-badge JSON file for the coverage "
            "percentage to PATH"
        ),
    )

    args = parser.parse_args()

    if args.command == "generate":
        description_provider = None
        if args.ai_draft:
            if args.inplace and not args.accept_ai_drafts:
                print(
                    "Error: --ai-draft with --inplace also requires "
                    "--accept-ai-drafts -- an explicit acknowledgment that "
                    "unreviewed AI-drafted text is being written straight "
                    "to your source files. Review with --dry-run or "
                    "--output-dir first, or pass --accept-ai-drafts."
                )
                sys.exit(1)
            try:
                description_provider = build_ai_provider(
                    args.ai_provider,
                    args.ai_model,
                    args.ai_base_url,
                    backend_url=os.environ.get(
                        "PYCODECOMMENTER_AI_BACKEND_URL", DEFAULT_BACKEND_URL
                    ),
                    assume_consent=args.yes_send_code_to_ai,
                )
            except AISetupError as e:
                print(f"Error: {e}")
                sys.exit(1)

        run_report = GenerationReport()
        try:
            _generate(args, description_provider, run_report)
        finally:
            # Runs however _generate exits (it calls sys.exit on several
            # paths), so the user always learns what the run did.
            if run_report.files:
                status("")
                for line in run_report.summary_lines(
                    preview=args.dry_run, ai_used=args.ai_draft
                ):
                    status(line)
            if description_provider is not None:
                report_ai_outcome(description_provider)

    elif args.command == "validate":
        if os.path.isdir(args.file):
            targets = _collect_py_files(args.file, args.exclude)
            if not targets:
                print(f"No Python files found in {args.file}")
                sys.exit(0)

            any_errors = False
            json_reports = []
            for target in targets:
                validator = DocstringValidator(file_path=target)
                report = validator.validate_all()
                if report.stats.errors > 0:
                    any_errors = True
                if args.output_format == "json":
                    json_reports.append(report.to_dict())
                else:
                    report.print_summary()

            if args.output_format == "json":
                print(json.dumps(json_reports, indent=2))
            if any_errors:
                sys.exit(1)
            return

        validator = DocstringValidator(file_path=args.file)
        report = validator.validate_all()
        if args.output_format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            report.print_summary()
        if report.stats.errors > 0:
            sys.exit(1)

    elif args.command == "coverage":
        analyzer = CoverageAnalyzer()
        if os.path.isdir(args.path):
            result = analyzer.analyze_directory(
                args.path, exclude_patterns=args.exclude
            )
            coverage_percentage = result.total_coverage
            if args.output_format == "json":
                print(json.dumps(result.to_json(), indent=2))
            else:
                result.print_report()
        else:
            try:
                result = analyzer.analyze_file(args.path)
            except (IOError, OSError, SyntaxError, UnicodeDecodeError) as e:
                print(f"Error: Could not analyze {args.path}: {e}", file=sys.stderr)
                sys.exit(1)
            coverage_percentage = result.coverage_percentage
            if args.output_format == "json":
                functions_ratio = (
                    f"{result.documented_functions}/{result.total_functions}"
                )
                classes_ratio = f"{result.documented_classes}/{result.total_classes}"
                file_dict = {
                    "file": args.path,
                    "coverage_percentage": round(result.coverage_percentage, 2),
                    "functions": functions_ratio,
                    "classes": classes_ratio,
                }
                print(json.dumps(file_dict, indent=2))
            else:
                print(f"Coverage for {args.path}: {result.coverage_percentage:.1f}%")

        if args.badge_output:
            with open(args.badge_output, "w") as f:
                json.dump(shields_badge_dict(coverage_percentage), f, indent=2)

        if args.fail_below is not None and coverage_percentage < args.fail_below:
            print(
                f"Coverage {coverage_percentage:.1f}% is below the "
                f"{args.fail_below}% threshold",
                file=sys.stderr,
            )
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
