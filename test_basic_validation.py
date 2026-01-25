from validator import DocstringValidator, Severity

# Test 1: Missing docstring detection
code_missing = """
def add(a, b):
    return a + b
"""

validator = DocstringValidator(code_string=code_missing)
report = validator.validate_all()
print(f"Test 1 - Missing docstring issues: {len(report.issues)}")
for issue in report.issues:
    print(issue)

# Test 2: Signature mismatch
code_mismatch = """
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

validator2 = DocstringValidator(code_string=code_mismatch)
report2 = validator2.validate_all()
print(f"\nTest 2 - Signature mismatch issues: {len(report2.issues)}")
for issue in report2.issues:
    print(issue)

# Test 3: Order mismatch
code_order = """
def subtract(a, b):
    '''Subtract.
    
    Args:
        b (int): Second
        a (int): First
    '''
    return a - b
"""
validator3 = DocstringValidator(code_string=code_order)
report3 = validator3.validate_all()
print(f"\nTest 3 - Order mismatch issues: {len(report3.issues)}")
for issue in report3.issues:
    print(issue)
