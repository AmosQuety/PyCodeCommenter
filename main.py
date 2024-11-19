# from PyCodeCommenter.commenter import PyCodeCommenter


import sys
import os


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from PyCodeCommenter.commenter import PyCodeCommenter

# Example functions for string input
code_string = """
class calc:
    def add(a: int, b: int) -> int:
        return a + b

    def greet(name: str) -> None:
        print(f"Hello, {name}!")
"""



# Define the file path for file input
# code_file = "C:\path\to\your\\file\example.py"

#  Create an instance of CodeCommenter based on your preferred input method

# Uncomment one of the lines below based on your input choice:

# For file input:
# commenter = PyCodeCommenter().from_file(code_file)

# For string input:
commenter = PyCodeCommenter().from_string(code_string)

# Generate docstrings
docstrings = commenter.generate_docstrings()

# Print the generated docstrings
for comment in docstrings:
    print(comment)

# OR Save docstrings to a file
# output_file = "C:\\Users\\DSN\\Desktop\\FileTransfer\\docstrings.txt"
# with open(output_file, 'w') as f:
#     for comment in docstrings:
#         f.write(comment + "\n\n")  # Add double newlines for separation

