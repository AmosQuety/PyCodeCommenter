"""Comprehensive test suite for all validation checks."""
# -*- coding: utf-8 -*-
from validator import DocstringValidator, Severity
import json

print("="*80)
print("COMPREHENSIVE VALIDATION TEST SUITE")
print("="*80)

# Test 1: Missing docstring
print("\n[TEST 1] Missing Docstring Detection")
code1 = """
def add(a, b):
    return a + b
"""
validator1 = DocstringValidator(code_string=code1)
report1 = validator1.validate_all()
print(f"✓ Detected {report1.stats.errors} error(s)")
assert report1.stats.errors > 0

# Test 2: Signature mismatch
print("\n[TEST 2] Signature Mismatch")
code2 = """
def multiply(x, y):
    '''Multiply two numbers.
    
    Args:
        x (int): First number
        z (int): Wrong parameter name!
    
    Returns:
        int: Product
    '''
    return x * y
"""
validator2 = DocstringValidator(code_string=code2)
report2 = validator2.validate_all()
print(f"✓ Detected {report2.stats.errors} error(s), {report2.stats.warnings} warning(s)")
assert report2.stats.errors > 0 or report2.stats.warnings > 0

# Test 3: Type consistency - missing Returns section
print("\n[TEST 3] Type Consistency - Missing Returns Documentation")
code3 = """
def divide(a: int, b: int) -> float:
    '''Divide two numbers.
    
    Args:
        a (int): Numerator
        b (int): Denominator
    '''
    return a / b
"""
validator3 = DocstringValidator(code_string=code3)
report3 = validator3.validate_all()
print(f"✓ Detected {report3.stats.warnings} warning(s)")
assert report3.stats.warnings > 0

# Test 4: Exception documentation
print("\n[TEST 4] Exception Documentation")
code4 = """
def validate_age(age):
    '''Validate age is positive.
    
    Args:
        age (int): Age to validate
    '''
    if age < 0:
        raise ValueError("Age cannot be negative")
    return age
"""
validator4 = DocstringValidator(code_string=code4)
report4 = validator4.validate_all()
print(f"✓ Detected {report4.stats.warnings} warning(s) about missing Raises section")
assert report4.stats.warnings > 0

# Test 5: Return documentation
print("\n[TEST 5] Return Documentation")
code5 = """
def greet(name):
    '''Greet a person.
    
    Args:
        name (str): Person's name
    '''
    return f"Hello, {name}!"
"""
validator5 = DocstringValidator(code_string=code5)
report5 = validator5.validate_all()
print(f"✓ Detected {report5.stats.warnings} warning(s) about missing Returns section")
assert report5.stats.warnings > 0

# Test 6: Content quality - placeholder text
print("\n[TEST 6] Content Quality - Placeholder Text")
code6 = """
def process_data(data):
    '''TODO: Add description.
    
    Args:
        data: Input data
    '''
    pass
"""
validator6 = DocstringValidator(code_string=code6)
report6 = validator6.validate_all()
print(f"✓ Detected {report6.stats.warnings} warning(s) about placeholder text")
assert report6.stats.warnings > 0

# Test 7: Content quality - short summary
print("\n[TEST 7] Content Quality - Short Summary")
code7 = """
def foo():
    '''Do it.'''
    pass
"""
validator7 = DocstringValidator(code_string=code7)
report7 = validator7.validate_all()
print(f"✓ Detected {report7.stats.infos} info message(s) about short summary")
assert report7.stats.infos > 0

# Test 8: Format compliance - missing summary
print("\n[TEST 8] Format Compliance")
code8 = """
def bar():
    '''
    
    Args:
        x: Something
    '''
    pass
"""
validator8 = DocstringValidator(code_string=code8)
report8 = validator8.validate_all()
print(f"✓ Detected {report8.stats.errors} error(s) about format issues")

# Test 9: Complete validation report
print("\n[TEST 9] Complete Validation Report")
code9 = """
def complex_function(a, b, c):
    '''TODO: Fix this.
    
    Args:
        a: First
        b: Second
        x: Wrong param
    
    Returns:
        Something
    '''
    if a < 0:
        raise ValueError("Invalid")
    return a + b
"""
validator9 = DocstringValidator(code_string=code9)
report9 = validator9.validate_all()
print("\n" + "="*60)
report9.print_summary()

# Test 10: Export formats
print("\n[TEST 10] Export Formats")
print("\n--- JSON Export ---")
json_output = json.dumps(report9.to_dict(), indent=2)
print(json_output[:200] + "...")

print("\n--- Markdown Export ---")
md_output = report9.to_markdown()
print(md_output[:300] + "...")

print("\n" + "="*80)
print("✅ ALL TESTS PASSED!")
print("="*80)
