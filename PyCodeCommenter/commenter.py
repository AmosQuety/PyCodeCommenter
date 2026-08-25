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
from typing import Union, Dict, Any, Optional
import libcst as cst
from libcst.metadata import PositionProvider

try:
    from .parameter_descriptions import parameter_descriptions
    from .inference import infer_description, humanize_identifier, GUESS_MARKER
    from .type_analyzer import TypeAnalyzer
    from .docstring_parser import DocstringParser
    from .param_utils import get_all_parameters, exclude_self_cls
except (ImportError, ValueError):
    from parameter_descriptions import parameter_descriptions
    from inference import infer_description, humanize_identifier, GUESS_MARKER
    from type_analyzer import TypeAnalyzer
    from docstring_parser import DocstringParser
    from param_utils import get_all_parameters, exclude_self_cls

# Configure logging
logger = logging.getLogger(__name__)


def _walk_function_body(func_node):
    """Yields every AST node in func_node's own body, without descending
    into nested function/class scopes.

    ``ast.walk(func_node)`` descends into nested FunctionDef/
    AsyncFunctionDef/ClassDef bodies too, so a ``return``/``yield`` inside a
    nested ``def`` would get misattributed to the outer function. This stops
    at those boundaries instead.
    """
    stack = list(func_node.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


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
        self.file_path = None

    def from_string(self, code_string: str) -> "PyCodeCommenter":
        """Initializes the commenter from a string of code."""
        self.file_path = None
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
                    self.tokenized_comments.append(
                        {"text": tok_string, "line": start[0], "column": start[1]}
                    )
        except Exception as e:
            logger.error(f"Error extracting comments: {e}")

    def from_file(self, file_path: str) -> "PyCodeCommenter":
        """Initializes the commenter from a file path."""
        self.file_path = file_path
        try:
            with open(file_path, "r", encoding="utf-8") as file:
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
        """Iterates over the parsed code to generate docstrings for functions
        and classes."""
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
        """Returns the code with generated docstrings inserted or updated.

        Uses libcst to apply edits at the concrete-syntax-tree level rather
        than by line-number arithmetic on the raw source text, so untouched
        code (including formatting, blank lines, and comments elsewhere in
        the file) round-trips unchanged and one-line definitions
        (e.g. ``def foo(): return 1``) are safely converted to a proper
        indented block instead of having the docstring inserted before the
        definition.
        """
        if not self.code or not self.parsed_code:
            return self.code

        visitor = DocstringVisitor(self)
        visitor.visit(self.parsed_code)

        if not visitor.results:
            return self.code

        edits = {
            (node.lineno, node.col_offset): docstring
            for node, docstring in visitor.results
        }

        try:
            module = cst.parse_module(self.code)
        except cst.ParserSyntaxError as e:
            logger.error(f"libcst failed to parse code for patching: {e}")
            return self.code

        wrapper = cst.MetadataWrapper(module)
        patched_module = wrapper.visit(_DocstringCSTPatcher(edits))
        return patched_module.code

    def _generate_function_docstring(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> str:
        """Generates a Google-style docstring for a function node, merging
        existing info."""
        try:
            existing_doc = ast.get_docstring(func_node)
            parser = DocstringParser(existing_doc)
            parsed_info = parser.get_info()

            summary = parsed_info.get("summary") or (
                humanize_identifier(func_node.name).capitalize() + "."
            )

            if func_node.name == "__init__":
                summary = "Initialize the class."
                description = (
                    parsed_info.get("description") or "Initialize a new instance."
                )
            else:
                # A preserved existing description is the author's real
                # words (a fact); anything templates.py.get_function_description()
                # would have guessed from the function's name alone is not,
                # so it's marked rather than presented as finished prose.
                description = parsed_info.get("description") or GUESS_MARKER

            if description and description.lower().rstrip(
                "."
            ) == summary.lower().rstrip("."):
                description = ""

            docstring = f'"""{summary}\n\n'
            if description:
                docstring += f"{description}\n\n"

            docstring += "Args:\n"

            # get_all_parameters() covers positional-only, positional-or-
            # keyword, *args, keyword-only, and **kwargs params -- the full
            # ast.arguments grammar, not just func_node.args.args -- so
            # signatures using any of those are no longer silently dropped.
            all_params = exclude_self_cls(get_all_parameters(func_node))
            sibling_params = [p.name for p in all_params]

            found_args = False
            for param in all_params:
                found_args = True
                # A real static type annotation is provably correct from
                # the code and always wins. Only fall back to a type
                # documented in an existing docstring when static
                # inference has nothing to offer ("any"). *args/**kwargs
                # collect into a tuple/dict at runtime regardless of
                # annotation, so that's used as the last-resort fact for them.
                static_type = self._infer_type(param.arg)
                if static_type == "any":
                    if param.kind == "vararg":
                        static_type = "tuple"
                    elif param.kind == "kwarg":
                        static_type = "dict"
                docstring_type = parsed_info.get("param_types", {}).get(
                    param.display_name
                )
                inferred_type = (
                    static_type
                    if static_type != "any"
                    else (docstring_type or static_type)
                )
                default_str = (
                    self._get_default_value(param.default)
                    if param.default is not None
                    else None
                )
                param_desc = parsed_info.get("params", {}).get(
                    param.display_name
                ) or self._get_parameter_description(
                    func_name=func_node.name,
                    param_name=param.name,
                    inferred_type=inferred_type,
                    default_value=default_str,
                    sibling_params=sibling_params,
                )

                display_type = "Any" if inferred_type == "any" else inferred_type
                arg_line = f"    {param.display_name} ({display_type}): {param_desc}"
                if not any(param_desc.endswith(p) for p in {".", "!", "?"}):
                    arg_line += "."
                if param.default is not None:
                    arg_line += f" (default: {self._get_default_value(param.default)})"
                docstring += arg_line + "\n"

            if not found_args:
                docstring += "    None.\n"

            local_types = self._get_local_types(func_node)
            is_generator = self._is_generator(func_node)
            return_type = self._get_return_type(func_node, local_types)
            display_return_type = "Any" if return_type == "any" else return_type
            section_label = "Yields" if is_generator else "Returns"

            existing_return_desc = parsed_info.get("returns")
            if existing_return_desc:
                return_desc = existing_return_desc
                if ":" in return_desc:
                    prefix, rest = return_desc.split(":", 1)
                    prefix_clean = prefix.strip()
                    if (
                        prefix_clean == return_type
                        or " " not in prefix_clean
                        or "[" in prefix_clean
                        or "|" in prefix_clean
                    ):
                        return_desc = rest.strip()
                docstring += (
                    f"\n{section_label}:\n    {display_return_type}: {return_desc}\n"
                )
            elif func_node.name == "__init__" and not is_generator:
                # Constructors implicitly return None -- Google style omits
                # Returns entirely rather than prompting to describe a value
                # that's never returned.
                pass
            elif return_type == "None":
                # No return statement anywhere in the body (or only bare
                # `return`s): there's nothing to describe, so skip the
                # guess-marker prompt.
                docstring += f"\n{section_label}:\n    None.\n"
            else:
                docstring += (
                    f"\n{section_label}:\n    {display_return_type}: {GUESS_MARKER}\n"
                )

            docstring += '"""'
            return docstring
        except Exception as e:
            logger.error(
                f"Error generating function docstring for {func_node.name}: {e}"
            )
            return '"""Error generating docstring."""'

    def _generate_class_docstring(self, class_node: ast.ClassDef) -> str:
        """Generates a Google-style docstring for a class node, merging
        existing info."""
        try:
            existing_doc = ast.get_docstring(class_node)
            parser = DocstringParser(existing_doc)
            parsed_info = parser.get_info()

            summary = parsed_info.get("summary") or f"{class_node.name} class."
            description = parsed_info.get("description") or GUESS_MARKER

            docstring = f'"""{summary}\n\n'
            if description:
                docstring += f"{description}\n\n"

            attributes = self._get_class_attributes(class_node)
            if attributes:
                docstring += "Attributes:\n"
                for attr, attr_type in attributes.items():
                    # We could also parse existing attributes if we added
                    # that to DocstringParser
                    docstring += f"    {attr} ({attr_type}): {GUESS_MARKER}\n"

            methods = [
                node.name
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith("_")
            ]
            if methods:
                docstring += "\nMethods:\n"
                for method in methods:
                    docstring += f"    {method}(): {GUESS_MARKER}\n"

            docstring += '"""'
            return docstring
        except Exception as e:
            logger.error(f"Error generating class docstring for {class_node.name}: {e}")
            return '"""Error generating docstring."""'

    def _get_parameter_description(
        self,
        func_name: str,
        param_name: str,
        inferred_type: str = None,
        default_value: str = None,
        sibling_params: list = None,
    ) -> str:
        """Retrieve a description for a parameter, using static dict as
        fallback and rule‑based inference as primary source.

        Args:
            func_name (str): Name of the function containing the parameter.
            param_name (str): Parameter name.
            inferred_type (str, optional): Inferred type hint for the parameter.
            default_value (str, optional): String representation of the default value.
            sibling_params (list, optional): List of other parameter names in
                the same function.

        Returns:
            str: Description of the parameter.
        """
        # First, try the static dictionary for explicit overrides.
        static_desc = parameter_descriptions.get(func_name, {}).get(param_name)
        if static_desc:
            return static_desc
        # Use rule‑based inference when possible.
        try:
            return infer_description(
                param_name=param_name,
                type_hint=inferred_type,
                default_value=default_value,
                function_name=func_name,
                sibling_params=sibling_params or [],
            )
        except Exception as e:
            # Inference failed, so there's nothing but a guess to offer here.
            logger.warning(f"Inference failed for {func_name}.{param_name}: {e}")
            return GUESS_MARKER

    def _get_class_attributes(self, class_node: ast.ClassDef) -> Dict[str, str]:
        """
        Extracts attributes from a class.

        Three sources, in this order: __init__'s own parameters, ``self.x =
        ...`` assignments anywhere in __init__'s body (for computed
        attributes that aren't also parameters), and class-level
        ``AnnAssign`` fields (covers ``@dataclass``-style classes with no
        __init__ written in source).

        Args:
            class_node (ast.ClassDef): The class node.

        Returns:
            Dict[str, str]: A dictionary mapping attribute names to their
                inferred types.
        """
        attributes = {}
        for item in class_node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "__init__"
            ):
                for arg in item.args.args[1:]:
                    attributes[arg.arg] = self._infer_type(arg)
                for node in ast.walk(item):
                    if (
                        isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Attribute)
                        and isinstance(node.targets[0].value, ast.Name)
                        and node.targets[0].value.id == "self"
                    ):
                        attr_name = node.targets[0].attr
                        if attr_name not in attributes:
                            attributes[attr_name] = self._infer_expr_type(node.value)

        for item in class_node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                attr_name = item.target.id
                if attr_name not in attributes:
                    attributes[attr_name] = self.type_analyzer.get_annotation_type(
                        item.annotation
                    )

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
        indent = " " * spaces
        return "\n".join(
            [indent + line if line.strip() else line for line in text.splitlines()]
        )

    def _infer_type(self, node: Any) -> str:
        """
        Infers the type of an AST node.

        Args:
            node (Any): The AST node.

        Returns:
            str: The inferred type.
        """
        return self.type_analyzer.infer_type(node)

    def _infer_expr_type(
        self, expr: Any, local_types: Optional[Dict[str, str]] = None
    ) -> str:
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

    def _is_generator(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> bool:
        """
        Determines whether a function is a generator (contains a yield in
        its own body).

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.

        Returns:
            bool: True if the function's own body contains a yield expression.
        """
        return any(
            isinstance(node, (ast.Yield, ast.YieldFrom))
            for node in _walk_function_body(func_node)
        )

    def _get_return_type(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        local_types: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Infers the return (or, for a generator, yield) type of a function.

        Only walks the function's own body -- not nested function/class
        definitions -- so a return/yield inside a nested def is never
        misattributed to the outer function.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            local_types (Optional[Dict[str, str]]): Known local types for
                better inference.

        Returns:
            str: The inferred return (or yield) type.
        """
        if func_node.returns:
            return self.type_analyzer.get_annotation_type(func_node.returns)

        if self._is_generator(func_node):
            value_nodes = [
                node
                for node in _walk_function_body(func_node)
                if isinstance(node, (ast.Yield, ast.YieldFrom))
                and node.value is not None
            ]
        else:
            value_nodes = [
                node
                for node in _walk_function_body(func_node)
                if isinstance(node, ast.Return) and node.value is not None
            ]

        value_types = {
            self._infer_expr_type(node.value, local_types) for node in value_nodes
        }

        filtered_types = {t for t in value_types if t != "any"}
        if not filtered_types and value_types:
            return "any"
        return " | ".join(sorted(filtered_types)) if filtered_types else "None"

    def _get_local_types(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> Dict[str, str]:
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
                        local_types[target.id] = self._infer_expr_type(
                            stmt.value, local_types
                        )
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

        validator = DocstringValidator(code_string=self.code, file_path=self.file_path)
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

        coverage = FileCoverage(path=self.file_path or "<string>")

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


class _DocstringCSTPatcher(cst.CSTTransformer):
    """Applies generated/updated docstrings to a libcst tree.

    Edits are keyed by the (line, column) of the def/class keyword, as
    reported by ast for the same source - this lets get_patched_code()
    keep reusing the existing ast-based DocstringVisitor to decide *what*
    docstring text each node needs, while this transformer handles *where*
    and *how* to apply it at the concrete-syntax-tree level.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, edits: Dict[Any, str]):
        self._edits = edits

    @staticmethod
    def _is_docstring_stmt(stmt) -> bool:
        return (
            isinstance(stmt, cst.SimpleStatementLine)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], cst.Expr)
            and isinstance(stmt.body[0].value, cst.SimpleString)
        )

    @staticmethod
    def _reindent_continuation_lines(text: str, spaces: int) -> str:
        # The first line is placed by libcst's own block indentation; only
        # continuation lines need their indentation baked into the string
        # literal's content.
        lines = text.splitlines()
        if len(lines) <= 1:
            return text
        indent = " " * spaces
        return "\n".join(
            [lines[0]] + [indent + line if line.strip() else line for line in lines[1:]]
        )

    def _patch(self, original_node, updated_node):
        pos = self.get_metadata(PositionProvider, original_node).start
        docstring = self._edits.get((pos.line, pos.column))
        if docstring is None:
            return updated_node

        reindented = self._reindent_continuation_lines(docstring, pos.column + 4)
        doc_line = cst.SimpleStatementLine(
            body=[cst.Expr(value=cst.SimpleString(value=reindented))]
        )

        body = updated_node.body
        if isinstance(body, cst.SimpleStatementSuite):
            # One-liner definition (e.g. `def foo(): return 1`) - convert
            # to an indented block so the docstring has its own line
            # instead of being inserted before the definition.
            original_stmt_line = cst.SimpleStatementLine(
                body=list(body.body),
                trailing_whitespace=body.trailing_whitespace,
            )
            new_body = cst.IndentedBlock(body=[doc_line, original_stmt_line])
            return updated_node.with_changes(body=new_body)

        stmts = list(body.body)
        if stmts and self._is_docstring_stmt(stmts[0]):
            old_line = stmts[0]
            stmts[0] = old_line.with_changes(
                body=[
                    old_line.body[0].with_changes(
                        value=cst.SimpleString(value=reindented)
                    )
                ]
            )
        else:
            stmts.insert(0, doc_line)
        return updated_node.with_changes(body=body.with_changes(body=stmts))

    def leave_FunctionDef(self, original_node, updated_node):
        return self._patch(original_node, updated_node)

    def leave_AsyncFunctionDef(self, original_node, updated_node):
        return self._patch(original_node, updated_node)

    def leave_ClassDef(self, original_node, updated_node):
        return self._patch(original_node, updated_node)
