"""
Main docstring generation module for PyCodeCommenter.

This module provides the core PyCodeCommenter class for automatically generating,
validating, and patching Google-style docstrings in Python code. It supports both
file and string input, preserves existing documentation, and integrates with the
validation and coverage analysis systems.

Classes:
    PyCodeCommenter: Main class for generating and patching Python docstrings
    DocstringVisitor: AST visitor for traversing and processing code nodes
"""
import ast
import tokenize
import io
import logging
from typing import Union, Dict, Any, Optional, List
try:
    from .templates import get_function_description
    from .parameter_descriptions import parameter_descriptions
    from .type_analyzer import TypeAnalyzer
    from .docstring_parser import DocstringParser
except (ImportError, ValueError):
    from templates import get_function_description
    from parameter_descriptions import parameter_descriptions
    from type_analyzer import TypeAnalyzer
    from docstring_parser import DocstringParser

# Configure logging
logger = logging.getLogger(__name__)

class PyCodeCommenter:
    """
    Main class for generating and patching Python docstrings.
    """
    def __init__(self):
        self.code = ""
        self.parsed_code = None
        self.comments = []
        self.tokenized_comments = []
        self.type_analyzer = TypeAnalyzer()

    def from_string(self, code_string: str) -> 'PyCodeCommenter':
        """Initializes the commenter from a string of code."""
        try:
            if code_string is None or code_string.strip() == "":
                logger.warning("No code provided. Proceeding with an empty string.")
                self.code = ""
                self.parsed_code = ast.Module(body=[])
            else:
                self.code = code_string
                self.parsed_code = ast.parse(self.code)
                self._extract_comments()
        except SyntaxError as e:
            logger.error(f"Syntax error in provided code: {e}")
            self.parsed_code = None
        return self

    def _extract_comments(self):
        """Extracts all comments from the code using the tokenize module."""
        try:
            self.tokenized_comments = []
            tokens = tokenize.generate_tokens(io.StringIO(self.code).readline)
            for tok_type, tok_string, start, end, line in tokens:
                if tok_type == tokenize.COMMENT:
                    self.tokenized_comments.append({
                        "text": tok_string,
                        "line": start[0],
                        "column": start[1]
                    })
        except Exception as e:
            logger.error(f"Error extracting comments: {e}")

    def from_file(self, file_path: str) -> 'PyCodeCommenter':
        """Initializes the commenter from a file path."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self.code = file.read()
            self.parsed_code = ast.parse(self.code)
            self._extract_comments()
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Error reading file: {e}")
            self.parsed_code = None
        except SyntaxError as e:
            logger.error(f"Syntax error in file: {e}")
            self.parsed_code = None
        return self

    def generate_docstrings(self) -> list:
        """Iterates over the parsed code to generate docstrings for functions and classes."""
        if self.parsed_code is None:
            logger.error("No valid code to parse.")
            return []

        self.comments = []
        
        # Module level docstring
        module_doc = ast.get_docstring(self.parsed_code)
        if module_doc:
            self.comments.append(f"Module Docstring:\n{module_doc}\n")

        visitor = DocstringVisitor(self)
        visitor.visit(self.parsed_code)
        
        for node, doc in visitor.results:
            self.comments.append(doc)
        
        return self.comments

    def get_patched_code(self) -> str:
        """Returns the code with generated docstrings inserted or updated."""
        if not self.code or not self.parsed_code:
            return self.code

        lines = self.code.splitlines()
        changes = []

        visitor = DocstringVisitor(self)
        visitor.visit(self.parsed_code)

        for node, docstring in visitor.results:
            existing_doc = ast.get_docstring(node, clean=False)
            
            # Find the line with 'def' or 'class' or 'async def'
            target_line_idx = node.lineno - 1
            while target_line_idx < len(lines):
                curr_line = lines[target_line_idx].strip()
                if curr_line.startswith(('def ', 'class ', 'async def ')):
                    break
                target_line_idx += 1
            
            if target_line_idx >= len(lines):
                continue
                
            line = lines[target_line_idx]
            indent = line[:len(line) - len(line.lstrip())]
            reindented_doc = self._indent_text(docstring, len(indent) + 4)

            if existing_doc:
                # Replace existing docstring
                doc_node = node.body[0]
                if isinstance(doc_node, ast.Expr) and isinstance(doc_node.value, ast.Constant) and isinstance(doc_node.value.value, str):
                    start = doc_node.lineno - 1
                    end = doc_node.end_lineno - 1 if hasattr(doc_node, 'end_lineno') else start
                    changes.append((start, end, reindented_doc))
            else:
                # Insert after the definition line(s)
                if node.body:
                    insert_pos = node.body[0].lineno - 1
                    changes.append((insert_pos, insert_pos - 1, reindented_doc))

        # Sort changes in reverse order
        changes.sort(key=lambda x: x[0], reverse=True)
        
        for start, end, content in changes:
            if start <= end:
                lines[start:end+1] = [content]
            else:
                lines.insert(start, content)
        
        return "\n".join(lines)

    def _generate_function_docstring(self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
        """Generates a Google-style docstring for a function node, merging existing info."""
        try:
            existing_doc = ast.get_docstring(func_node)
            parser = DocstringParser(existing_doc)
            parsed_info = parser.get_info()
            
            summary = parsed_info.get("summary") or (func_node.name.replace('_', ' ').capitalize() + ".")
            
            if func_node.name == "__init__":
                summary = "Initialize the class."
                description = parsed_info.get("description") or "Initialize a new instance."
            else:
                description = parsed_info.get("description") or get_function_description(func_node.name)

            if description and description.lower().rstrip('.') == summary.lower().rstrip('.'):
                description = ""

            docstring = f'"""{summary}\n\n'
            if description:
                docstring += f"{description}\n\n"

            docstring += "Args:\n"
            defaults = [None] * (len(func_node.args.args) - len(func_node.args.defaults)) + func_node.args.defaults

            found_args = False
            for arg, default in zip(func_node.args.args, defaults):
                if arg.arg == 'self':
                    continue
                found_args = True
                inferred_type = self._infer_type(arg)
                # Use parser to get existing parameter description
                param_desc = parsed_info.get("params", {}).get(arg.arg) or self._get_parameter_description(func_node.name, arg.arg)
                
                arg_line = f"    {arg.arg} ({inferred_type}): {param_desc}"
                if not any(param_desc.endswith(p) for p in {'.', '!', '?'}):
                    arg_line += "."
                if default is not None:
                    arg_line += f" (default: {self._get_default_value(default)})"
                docstring += arg_line + "\n"

            if not found_args:
                docstring += "    None.\n"

            local_types = self._get_local_types(func_node)
            return_type = self._get_return_type(func_node, local_types)
            return_desc = parsed_info.get("returns") or "Description of the return value."
            
            docstring += f"\nReturns:\n    {return_type}: {return_desc}\n"
            docstring += '"""'
            return docstring
        except Exception as e:
            logger.error(f"Error generating function docstring for {func_node.name}: {e}")
            return '"""Error generating docstring."""'

    def _generate_class_docstring(self, class_node: ast.ClassDef) -> str:
        """Generates a Google-style docstring for a class node, merging existing info."""
        try:
            existing_doc = ast.get_docstring(class_node)
            parser = DocstringParser(existing_doc)
            parsed_info = parser.get_info()
            
            summary = parsed_info.get("summary") or f"{class_node.name} class."
            description = parsed_info.get("description") or f"{class_node.name} class for [describe purpose]."
            
            docstring = f'"""{summary}\n\n'
            if description:
                docstring += f"{description}\n\n"

            attributes = self._get_class_attributes(class_node)
            if attributes:
                docstring += "Attributes:\n"
                for attr, attr_type in attributes.items():
                    # We could also parse existing attributes if we added that to DocstringParser
                    docstring += f"    {attr} ({attr_type}): Description of attribute.\n"

            methods = [node.name for node in class_node.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_')]
            if methods:
                docstring += "\nMethods:\n"
                for method in methods:
                    docstring += f"    {method}(): Description of method.\n"

            docstring += '"""'
            return docstring
        except Exception as e:
            logger.error(f"Error generating class docstring for {class_node.name}: {e}")
            return '"""Error generating docstring."""'

    def _get_parameter_description(self, func_name: str, param_name: str) -> str:
        """
        Retrieves a default or predefined description for a parameter.
        
        Args:
            func_name (str): The name of the function.
            param_name (str): The name of the parameter.
            
        Returns:
            str: The description of the parameter.
        """
        return parameter_descriptions.get(func_name, {}).get(param_name, f"{param_name.replace('_', ' ').capitalize()} of the {func_name.replace('_', ' ')}.")

    def _get_class_attributes(self, class_node: ast.ClassDef) -> Dict[str, str]:
        """
        Extracts attributes from a class by looking at __init__.
        
        Args:
            class_node (ast.ClassDef): The class node.
            
        Returns:
            Dict[str, str]: A dictionary mapping attribute names to their inferred types.
        """
        attributes = {}
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                for arg in item.args.args[1:]:
                    attributes[arg.arg] = self._infer_type(arg)
        return attributes

    def _indent_text(self, text: str, spaces: int) -> str:
        """
        Indents a block of text.
        
        Args:
            text (str): The text to indent.
            spaces (int): The number of spaces to indent by.
            
        Returns:
            str: The indented text.
        """
        indent = ' ' * spaces
        return "\n".join([indent + line if line.strip() else line for line in text.splitlines()])

    def _infer_type(self, node: Any) -> str:
        """
        Infers the type of an AST node.
        
        Args:
            node (Any): The AST node.
            
        Returns:
            str: The inferred type.
        """
        return self.type_analyzer.infer_type(node)

    def _infer_expr_type(self, expr: Any, local_types: Optional[Dict[str, str]] = None) -> str:
        """
        Infers the type of an expression node.
        
        Args:
            expr (Any): The expression node.
            local_types (Optional[Dict[str, str]]): Dictionary of known local types.
            
        Returns:
            str: The inferred type.
        """
        return TypeAnalyzer(local_types).infer_expr_type(expr)

    def _get_default_value(self, default_node: Any) -> str:
        """
        Gets the string representation of a default value.
        
        Args:
            default_node (Any): The AST node for the default value.
            
        Returns:
            str: String representation of the default value.
        """
        if isinstance(default_node, ast.Constant):
            return repr(default_node.value)
        return "unknown"

    def _get_return_type(self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef], local_types: Optional[Dict[str, str]] = None) -> str:
        """
        Infers the return type of a function.
        
        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            local_types (Optional[Dict[str, str]]): Known local types for better inference.
            
        Returns:
            str: The inferred return type.
        """
        if func_node.returns:
            return self.type_analyzer.get_annotation_type(func_node.returns)
        return_types = set()
        for stmt in ast.walk(func_node):
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                return_types.add(self._infer_expr_type(stmt.value, local_types))
        
        filtered_types = {t for t in return_types if t != "any"}
        if not filtered_types and return_types:
            return "any"
        return " | ".join(sorted(filtered_types)) if filtered_types else "None"

    def _get_local_types(self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Dict[str, str]:
        """
        Extracts local variable types within a function.
        
        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            
        Returns:
            Dict[str, str]: Mapping of variable names to their inferred types.
        """
        local_types = {}
        for stmt in func_node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        local_types[target.id] = self._infer_expr_type(stmt.value, local_types)
        return local_types

    def validate(self, strict: bool = False):
        """
        Validate existing docstrings against code using comprehensive checks.
        
        Args:
            strict (bool): If True, treat warnings as errors. (default: False)
        
        Returns:
            ValidationReport: Comprehensive validation report with all issues found.
                             Returns empty report if no code is parsed.
        """
        try:
            from .validator import DocstringValidator, ValidationReport
        except (ImportError, ValueError):
            from validator import DocstringValidator, ValidationReport
        
        if self.parsed_code is None:
            logger.error("No valid code parsed for validation.")
            # Return empty report instead of None
            empty_report = ValidationReport()
            empty_report.file_path = None
            return empty_report
        
        validator = DocstringValidator(code_string=self.code, file_path=None)
        report = validator.validate_all()
        
        return report
    
    def check_coverage(self):
        """
        Calculate documentation coverage for current code.
        
        Returns:
            FileCoverage: Coverage statistics for the current code.
        """
        try:
            from .coverage import FileCoverage
        except (ImportError, ValueError):
            from coverage import FileCoverage
        
        if self.parsed_code is None:
            logger.error("No valid code parsed for coverage analysis.")
            # Return empty coverage instead of None
            return FileCoverage(path="<no code>")
        
        coverage = FileCoverage(path="<string>")
        
        for node in ast.walk(self.parsed_code):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                coverage.total_functions += 1
                if ast.get_docstring(node):
                    coverage.documented_functions += 1
            elif isinstance(node, ast.ClassDef):
                coverage.total_classes += 1
                if ast.get_docstring(node):
                    coverage.documented_classes += 1
        
        return coverage

class DocstringVisitor(ast.NodeVisitor):
    def __init__(self, commenter):
        self.commenter = commenter
        self.results = []
    
    def visit_FunctionDef(self, node):
        self.results.append((node, self.commenter._generate_function_docstring(node)))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.results.append((node, self.commenter._generate_function_docstring(node)))
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.results.append((node, self.commenter._generate_class_docstring(node)))
        self.generic_visit(node)

