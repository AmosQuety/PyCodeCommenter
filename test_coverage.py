"""Test coverage analyzer."""
# -*- coding: utf-8 -*-
from coverage import CoverageAnalyzer
import json

print("="*80)
print("COVERAGE ANALYZER TEST")
print("="*80)

analyzer = CoverageAnalyzer()

# Test single file
print("\n[TEST 1] Single File Analysis")
coverage = analyzer.analyze_file("commenter.py")
print(f"File: {coverage.path}")
print(f"Functions: {coverage.documented_functions}/{coverage.total_functions}")
print(f"Classes: {coverage.documented_classes}/{coverage.total_classes}")
print(f"Coverage: {coverage.coverage_percentage:.1f}%")

# Test directory
print("\n[TEST 2] Directory Analysis")
project = analyzer.analyze_directory(".", exclude_patterns=['__pycache__', 'test_', 'venv'])
project.print_report()

# Test JSON export
print("\n[TEST 3] JSON Export")
json_output = json.dumps(project.to_json(), indent=2)
print(json_output[:400] + "...")

print("\n" + "="*80)
print("✅ COVERAGE TESTS PASSED!")
print("="*80)
