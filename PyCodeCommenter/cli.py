"""
CLI entry point for PyCodeCommenter.
"""
import sys
import json
import argparse
import os
import difflib
import shutil
from .commenter import PyCodeCommenter
from .validator import DocstringValidator
from .coverage import CoverageAnalyzer

def main():
    parser = argparse.ArgumentParser(description="PyCodeCommenter CLI - Automatic docstring generation and validation.")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command
    generate_parser = subparsers.add_parser("generate", help="Generate docstrings for a file")
    generate_parser.add_argument("file", help="Python file to process")
    generate_parser.add_argument("-i", "--inplace", action="store_true", help="Modify file in place")
    generate_parser.add_argument("-o", "--output", help="Output file path")
    generate_parser.add_argument("--dry-run", action="store_true", help="Show diff without writing any files")
    generate_parser.add_argument("--backup", action="store_true", help="Create a .bak backup before inplace modification")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate docstrings for a file")
    validate_parser.add_argument("file", help="Python file to validate")
    validate_parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: 'text' (default) or 'json'",
    )

    # Coverage command
    coverage_parser = subparsers.add_parser("coverage", help="Analyze documentation coverage")
    coverage_parser.add_argument("path", help="Directory or file to analyze")
    coverage_parser.add_argument("-e", "--exclude", nargs="*", help="Patterns to exclude")
    coverage_parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        metavar="FORMAT",
        help="Output format: 'text' (default) or 'json'",
    )

    args = parser.parse_args()

    if args.command == "generate":
        commenter = PyCodeCommenter().from_file(args.file)
        if not commenter.parsed_code:
            print(f"Error: Could not parse {args.file}")
            sys.exit(1)
        
        patched_code = commenter.get_patched_code()

        if args.backup and not args.inplace:
            print("Warning: --backup has no effect without --inplace")

        # Dry-run: show diff and exit without writing
        if args.dry_run:
            with open(args.file, 'r', encoding='utf-8') as f:
                original_code = f.read()
            diff_lines = list(difflib.unified_diff(
                original_code.splitlines(),
                patched_code.splitlines(),
                fromfile=args.file,
                tofile=args.file,
                lineterm=''
            ))
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
            with open(args.file, 'w', encoding='utf-8') as f:
                f.write(patched_code)
            print(f"Successfully patched {args.file}")
        elif args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(patched_code)
            print(f"Successfully wrote patched code to {args.output}")
        else:
            print(patched_code)

    elif args.command == "validate":
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
            result = analyzer.analyze_directory(args.path, exclude_patterns=args.exclude)
            if args.output_format == "json":
                print(json.dumps(result.to_json(), indent=2))
            else:
                result.print_report()
        else:
            result = analyzer.analyze_file(args.path)
            if args.output_format == "json":
                file_dict = {
                    "file": args.path,
                    "coverage_percentage": round(result.coverage_percentage, 2),
                    "functions": f"{result.documented_functions}/{result.total_functions}",
                    "classes": f"{result.documented_classes}/{result.total_classes}",
                }
                print(json.dumps(file_dict, indent=2))
            else:
                print(f"Coverage for {args.path}: {result.coverage_percentage:.1f}%")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
