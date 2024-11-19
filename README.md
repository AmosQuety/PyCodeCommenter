# PyCodeCommenter Documentation

Welcome to the PyCodeCommenter documentation. This README file provides an overview of the project, including setup instructions, usage guidelines, and other relevant information.

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Usage](#usage)
- [License](#license)

## Introduction

**PyCodeCommenter** is a Python library designed to automatically generate Google-style docstrings for Python functions and classes. It analyzes your code and provides structured documentation that enhances code readability and maintainability. The library supports both direct code input as strings and file input, making it flexible for different use cases.

## Installation

1. Clone the repository:

```bash

```

2. Install dependencies:

```bash

```

## Usage

To use the PyCodeCommenter library, follow these steps to generate docstrings for your Python code. You can provide code through either direct string input or by reading from a Python file.

String Input Method
You can use the from_string method to directly input code as a string. Here’s an example:

```
from PyCodeCommenter.commenter import PyCodeCommenter

code_string = """
def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> None:
    print(f"Hello, {name}!")
"""

# Create an instance and use the string input method
commenter = PyCodeCommenter().from_string(code_string)

# Generate docstrings and print them
docstrings = commenter.generate_docstrings()
for docstring in docstrings:
    print(docstring)

```

File Input Method
To read code from a file, use the from_file method. Here’s an example:

```
from PyCodeCommenter.commenter import PyCodeCommenter

# Specify the path to your Python file
code_file = "path/to/your/code.py"

# Create an instance and use the file input method
commenter = PyCodeCommenter().from_file(code_file)

# Generate docstrings and print them
docstrings = commenter.generate_docstrings()
for docstring in docstrings:
    print(docstring)

```

You can choose between the two methods depending on your needs. The library is designed to be user-friendly and efficient, allowing you to seamlessly integrate documentation generation into your development workflow.

Features
Automatic Docstring Generation: Automatically creates Google-style docstrings for functions and classes in your code, improving documentation quality and consistency.

Support for Both Input Methods: Allows users to input code as a string or read from a Python file, providing flexibility based on user preference.

Type Annotations Handling: Analyzes and incorporates Python type annotations into the generated docstrings, ensuring that the documentation accurately reflects the function signatures.

Error Handling: Provides meaningful error messages for unsupported code structures or syntax errors, making it easier to troubleshoot issues.

Editable Installation: Supports editable installation, allowing developers to make changes to the library and see the effects without reinstalling.

Robust Testing: Includes unit tests to ensure reliability and accuracy of the documentation generation process.


## License

This project is licensed under the [MIT License](LICENSE).
