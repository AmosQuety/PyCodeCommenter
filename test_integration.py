"""Integration test for PyCodeCommenter with new validation and coverage features."""
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from commenter import PyCodeCommenter

print("="*80)
print("PYCODE COMMENTER - PHASE 3 INTEGRATION TEST")
print("="*80)

# Test code with various issues
test_code = """
def add(a, b):
    '''Add two numbers.
    
    Args:
        a (int): First number
        b (int): Second number
    
    Returns:
        int: Sum of a and b
    '''
    return a + b

def subtract(x, y):
    '''Subtract y from x.
    
    Args:
        a (int): Wrong parameter name
        b (int): Another wrong name
    '''
    return x - y

def divide(numerator: int, denominator: int) -> float:
    '''Divide two numbers.
    
    Args:
        numerator (int): The numerator
        denominator (int): The denominator
    '''
    if denominator == 0:
        raise ValueError("Cannot divide by zero")
    return numerator / denominator

class Calculator:
    '''Calculator class.'''
    
    def multiply(self, a, b):
        return a * b

def no_docs(param1, param2):
    return param1 + param2
"""

# Initialize commenter
commenter = PyCodeCommenter()
commenter.from_string(test_code)

# Test 1: Validation
print("\n[TEST 1] Comprehensive Validation")
print("-" * 80)
report = commenter.validate()
if report:
    report.print_summary()
else:
    print("No validation report generated")

# Test 2: Coverage Analysis
print("\n[TEST 2] Coverage Analysis")
print("-" * 80)
coverage = commenter.check_coverage()
if coverage:
    print(f"File: {coverage.path}")
    print(f"Functions: {coverage.documented_functions}/{coverage.total_functions}")
    print(f"Classes: {coverage.documented_classes}/{coverage.total_classes}")
    print(f"Coverage: {coverage.coverage_percentage:.1f}%")
else:
    print("No coverage data generated")

# Test 3: Export validation report as JSON
print("\n[TEST 3] JSON Export")
print("-" * 80)
if report:
    import json
    json_data = report.to_dict()
    print(json.dumps(json_data, indent=2)[:500] + "...")

# Test 4: Export validation report as Markdown
print("\n[TEST 4] Markdown Export")
print("-" * 80)
if report:
    md_report = report.to_markdown()
    print(md_report[:600] + "...")

print("\n" + "="*80)
print("✅ INTEGRATION TEST COMPLETE!")
print("="*80)
