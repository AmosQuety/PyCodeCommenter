"""
CLI entry point for PyCodeCommenter.
"""
import sys
import argparse
import os
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

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate docstrings for a file")
    validate_parser.add_argument("file", help="Python file to validate")

    # Coverage command
    coverage_parser = subparsers.add_parser("coverage", help="Analyze documentation coverage")
    coverage_parser.add_argument("path", help="Directory or file to analyze")
    coverage_parser.add_argument("-e", "--exclude", nargs="*", help="Patterns to exclude")

    args = parser.parse_args()

    if args.command == "generate":
        commenter = PyCodeCommenter().from_file(args.file)
        if not commenter.parsed_code:
            print(f"Error: Could not parse {args.file}")
            sys.exit(1)
        
        patched_code = commenter.get_patched_code()
        
        if args.inplace:
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
        report.print_summary()
        if report.stats.errors > 0:
            sys.exit(1)

    elif args.command == "coverage":
        analyzer = CoverageAnalyzer()
        if os.path.isdir(args.path):
            result = analyzer.analyze_directory(args.path, exclude_patterns=args.exclude)
            result.print_report()
        else:
            result = analyzer.analyze_file(args.path)
            # FileCoverage doesn't have a print_report method in the same way, but we can print its stats
            print(f"Coverage for {args.path}: {result.coverage_percentage:.1f}%")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
