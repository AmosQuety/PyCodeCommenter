import sys, os
sys.path.append(r'g:/MyProjects/new code/PyCodeCommenter')
from PyCodeCommenter import PyCodeCommenter

code = '''def calculate_price(price: float, tax_rate: float = 0.2, is_discounted: bool = False):
    """Calculate final price.
    """
    return price * (1 + tax_rate) * (0.9 if is_discounted else 1)
'''
commenter = PyCodeCommenter().from_string(code)
print('\n--- Generated Docstrings ---')
for doc in commenter.generate_docstrings():
    print(doc)

# Also show patched code
print('\n--- Patched Code ---')
print(commenter.get_patched_code())
