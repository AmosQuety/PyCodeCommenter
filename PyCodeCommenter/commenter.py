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
import inspect
import re
import tokenize
import io
import logging
from pathlib import Path
from typing import Union, Dict, Any, Optional
import libcst as cst
from libcst.metadata import PositionProvider

try:
    from .inference import (
        infer_description,
        has_name_signal,
        humanize_identifier,
        GUESS_MARKER,
    )
    from .type_analyzer import TypeAnalyzer
    from .docstring_parser import DocstringParser
    from .param_utils import (
        get_all_parameters,
        exclude_self_cls,
        walk_own_scope,
        walk_skipping_nested_classes,
    )
    from .description_provider import (
        DescriptionProvider,
        DraftingStopped,
        FunctionContext,
        ParameterFact,
    )
    from .ai_drafting import apply_draft, known_text, slots_for
    from .code_facts import (
        describe_bool_return,
        describe_raise_condition,
        raise_sites,
    )
    from .function_doc import (
        ArgEntry,
        DocPart,
        FunctionDoc,
        Origin,
        RaisesEntry,
        ReturnsEntry,
        render_function_doc,
    )
except (ImportError, ValueError):
    from inference import (
        infer_description,
        has_name_signal,
        humanize_identifier,
        GUESS_MARKER,
    )
    from type_analyzer import TypeAnalyzer
    from docstring_parser import DocstringParser
    from param_utils import (
        get_all_parameters,
        exclude_self_cls,
        walk_own_scope,
        walk_skipping_nested_classes,
    )
    from description_provider import (
        DescriptionProvider,
        DraftingStopped,
        FunctionContext,
        ParameterFact,
    )
    from ai_drafting import apply_draft, known_text, slots_for
    from code_facts import describe_bool_return, describe_raise_condition, raise_sites
    from function_doc import (
        ArgEntry,
        DocPart,
        FunctionDoc,
        Origin,
        RaisesEntry,
        ReturnsEntry,
        render_function_doc,
    )

# Configure logging
logger = logging.getLogger(__name__)

# One whole string literal: optional prefix, matching quotes, and a body
# that doesn't itself contain the closing quotes (which would mean implicit
# concatenation of several literals).
_STRING_QUOTES = ('"""', "'''", '"', "'")
_DOCSTRING_LITERAL_RE = re.compile(
    r"^(?P<prefix>[rRuU]{0,2})(?P<quote>"
    + "|".join(re.escape(quote) for quote in _STRING_QUOTES)
    + r")(?P<body>(?:(?!(?P=quote)).)*?)(?P=quote)$",
    re.DOTALL,
)


def _is_carried_forward(text: Optional[str]) -> bool:
    """Whether existing docstring text is real content worth keeping.

    Text containing the guess marker was written by an earlier run of this
    tool, not by an author, so it is regenerated rather than preserved.
    """
    return bool(text) and GUESS_MARKER not in text


# Matches the tool's own " (default: ...)" suffix (see the Args: loop's
# append in _generate_function_docstring), wherever it trails a re-parsed
# parameter description -- regardless of what value it names. It must be
# recognized unconditionally, not only when it happens to match the
# parameter's *current* default: the append step immediately below always
# re-adds the correct, current one regardless of what's stripped here.
_TRAILING_DEFAULT_ANNOTATION_RE = re.compile(r" \(default: .*\)$")


class PyCodeCommenter:
    """
    Main class for generating and patching Python docstrings.
    """

    def __init__(
        self,
        description_provider: Optional[DescriptionProvider] = None,
        include_module_docstrings: bool = False,
    ):
        """
        Args:
            description_provider (Optional[DescriptionProvider]): Opt-in
                source of AI-assisted free-text descriptions (see
                ``description_provider.py``). ``None`` (the default)
                preserves the tool's entire deterministic behavior -- no
                CLI command passes one unless ``--ai-draft`` is given, so
                this is only reachable by explicit opt-in.
            include_module_docstrings (bool): Opt-in module-level docstring
                generation for a module that has none at all (see
                ``_generate_module_docstring``). ``False`` by default:
                unlike a missing function/class docstring, a missing
                module docstring touches the output of nearly every input
                (any file/snippet with no module docstring, not just a
                main.py-shaped project file), so this stays off unless a
                caller explicitly asks for it -- consistent with every
                other consequential behavior in this tool (``--inplace``,
                ``--backup``, an AI description provider) requiring
                explicit opt-in rather than a silent default change.
        """
        self.code = ""
        self.parsed_code = None
        self.comments = []
        self.tokenized_comments = []
        self.type_analyzer = TypeAnalyzer()
        self.file_path = None
        self._description_provider = description_provider
        # Set once a provider says it can't draft any more this run (for
        # example, the daily allowance is spent); later functions keep
        # their gaps and the CLI reports why.
        self.drafting_stopped: Optional[DraftingStopped] = None
        self._include_module_docstrings = include_module_docstrings
        self._newline = "\n"

    def _normalize_newlines(self, raw_code: str) -> str:
        """Detects the source's newline convention and normalizes to
        ``\\n`` for internal processing.

        AST/libcst parsing and every regex/docstring-generation literal in
        this codebase assume ``\\n``; remembering the original convention
        here lets ``get_patched_code()`` restore it on output, instead of
        every CRLF file silently coming out as LF -- turning a documentation
        PR on such a file into a full-file line-ending diff even when zero
        docstrings actually changed.

        Args:
            raw_code (str): The source text, in its original line-ending
                convention.

        Returns:
            str: The same text with ``\\r\\n`` normalized to ``\\n``.
        """
        if "\r\n" in raw_code:
            self._newline = "\r\n"
            return raw_code.replace("\r\n", "\n")
        self._newline = "\n"
        return raw_code

    def from_string(self, code_string: str) -> "PyCodeCommenter":
        """Initializes the commenter from a string of code."""
        self.file_path = None
        self._newline = "\n"
        try:
            if code_string is None or code_string.strip() == "":
                logger.warning("No code provided. Proceeding with an empty string.")
                self.code = ""
                self.parsed_code = ast.Module(body=[])
            else:
                self.code = self._normalize_newlines(code_string)
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
        self._newline = "\n"
        try:
            # newline="" disables universal-newlines translation, so a
            # CRLF file's "\r\n" is still there to detect -- the default
            # text mode would have already silently converted it to "\n"
            # before we ever saw it.
            with open(file_path, "r", encoding="utf-8", newline="") as file:
                self.code = self._normalize_newlines(file.read())
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

        if not visitor.results and visitor.module_docstring is None:
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
        patched_module = wrapper.visit(
            _DocstringCSTPatcher(edits, module_docstring=visitor.module_docstring)
        )
        result = patched_module.code
        if self._newline == "\r\n":
            # Every internal literal in this codebase is written in "\n";
            # restore the source's original convention only at this final
            # boundary, so a CRLF file's documentation PR doesn't touch
            # every line's ending along with the actual docstring changes.
            result = result.replace("\n", "\r\n")
        return result

    def _default_module_summary(self) -> str:
        """Derives a module docstring's summary line when there's no
        existing one to preserve.

        A module has no name of its own the way a function/class node
        does -- the closest real signal is the file it came from, when
        there is one (``from_file``, or the CLI, which is how this gap
        matters in practice). ``from_string`` input has no such signal at
        all, so it gets a neutral, honest placeholder rather than an
        invented one.

        Returns:
            str: The summary line, without a trailing period already
                applied by the caller (a bare word/phrase).
        """
        if self.file_path:
            stem = Path(self.file_path).stem
            return humanize_identifier(stem).capitalize() + "."
        return "Module docstring."

    def _generate_module_docstring(self, module_node: ast.Module) -> str:
        """Generates a Google-style module docstring.

        Only ever called for a module with no existing docstring at all
        (see DocstringVisitor.visit_Module) -- unlike function/class
        docstrings, this never attempts to merge into an existing one.
        Module docstrings are much more free-form/hand-written prose than
        function/class ones; parsing and reconstructing an existing one
        risks corrupting it for no real benefit, when the actual gap this
        closes (AUDIT_REPORT.md §2) is files with *no* docstring at all.

        Args:
            module_node (ast.Module): The module node.

        Returns:
            str: The generated module docstring, including the enclosing
                triple quotes.
        """
        try:
            summary = self._default_module_summary()

            # A real, AST-derived fact about the module -- what it defines
            # -- costs nothing to include and mirrors the Attributes:/
            # Methods: pattern already used for classes, one level up.
            classes = [n.name for n in module_node.body if isinstance(n, ast.ClassDef)]
            functions = [
                n.name
                for n in module_node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

            sections = []
            if classes:
                sections.append(
                    "Classes:\n" + "".join(f"    {name}\n" for name in classes)
                )
            if functions:
                sections.append(
                    "Functions:\n" + "".join(f"    {name}\n" for name in functions)
                )

            if not sections:
                # Nothing to list beyond the summary -- close on the same
                # line rather than a gratuitous two-line docstring for a
                # single sentence.
                return f'"""{summary}"""'

            body = "\n".join(sections).rstrip("\n")
            return f'"""{summary}\n\n{body}\n"""'
        except Exception as e:
            logger.error(f"Error generating module docstring: {e}")
            return '"""Error generating docstring."""'

    def _existing_docstring(self, node: ast.AST) -> "tuple[Optional[str], str]":
        """A node's docstring as written in the source, and its prefix.

        ``ast.get_docstring`` returns the string's *value*, with escape
        sequences already interpreted (``\\n`` becomes a real line break).
        Writing that value back into a new literal silently changed the
        docstring on every run. Reading the literal's source text instead
        keeps escapes as written; the prefix (``"r"`` for a raw string, else
        ``""``) must be kept too, or a raw string's backslashes would start
        meaning escapes.

        Args:
            node (ast.AST): A function, class, or module node.

        Returns:
            tuple[Optional[str], str]: The cleaned docstring text (``None``
                if there is none) and the prefix to write it back with.
                Anything unusual -- implicit string concatenation, a
                triple quote inside a single-quoted literal -- falls back
                to ``ast.get_docstring``'s value with no prefix.
        """
        value = ast.get_docstring(node)
        if value is None:
            return None, ""
        literal = ast.get_source_segment(self.code, node.body[0].value)
        match = _DOCSTRING_LITERAL_RE.match(literal or "")
        if match is None or '"""' in match.group("body"):
            return value, ""
        prefix = "r" if "r" in match.group("prefix").lower() else ""
        return inspect.cleandoc(match.group("body")), prefix

    def _generate_function_docstring(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> str:
        """Generates a Google-style docstring for a function node, merging
        existing info."""
        existing_doc, prefix = None, ""
        try:
            existing_doc, prefix = self._existing_docstring(func_node)
            parsed_info = DocstringParser(existing_doc).get_info()
            return prefix + render_function_doc(
                self._build_function_doc(func_node, parsed_info)
            )
        except Exception as e:
            logger.error(
                f"Error generating function docstring for {func_node.name}: {e}"
            )
            if existing_doc is not None:
                # An unexpected failure mid-generation must not silently
                # discard whatever the author's real, existing docstring
                # was -- that's quiet data loss, not a safe fallback.
                # Falling back to the original text (matching the fallback
                # discipline already used for a libcst parse failure
                # elsewhere in this file) is always safer than replacing
                # real content with a placeholder.
                return f'{prefix}"""{existing_doc}"""'
            return '"""Error generating docstring."""'

    def _build_function_doc(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parsed_info: Dict[str, Any],
    ) -> FunctionDoc:
        """Collects every part of a function's docstring, each tagged with
        where its text came from (see ``function_doc.Origin``).

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.
            parsed_info (Dict[str, Any]): The existing docstring, parsed.

        Returns:
            FunctionDoc: The parts, ready to render.
        """
        summary = self._summary_part(func_node, parsed_info)
        doc = FunctionDoc(
            summary=summary,
            description=self._description_part(parsed_info, summary),
            args=self._arg_entries(func_node, parsed_info),
            returns=self._returns_entry(func_node, parsed_info),
            raises=self._raises_entries(func_node, parsed_info.get("raises", {})),
        )
        self._fill_gaps_with_provider(func_node, doc)
        return doc

    def _fill_gaps_with_provider(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef], doc: FunctionDoc
    ) -> None:
        """Asks the opt-in description provider to draft the docstring's
        gaps, failing closed: any error leaves the gaps as they are.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.
            doc (FunctionDoc): The docstring parts, updated in place.
        """
        if self._description_provider is None or self.drafting_stopped is not None:
            return
        slots = slots_for(doc)
        if slots.is_empty():
            return
        try:
            draft = self._description_provider.draft_docstring(
                self._build_function_context(func_node), known_text(doc), slots
            )
        except DraftingStopped as e:
            self.drafting_stopped = e
            return
        except Exception as e:
            logger.warning(
                f"Description provider failed for {func_node.name}, "
                f"leaving its gaps as they are: {e}"
            )
            return
        apply_draft(doc, draft, slots)

    def _summary_part(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parsed_info: Dict[str, Any],
    ) -> DocPart:
        if func_node.name == "__init__":
            # "Initialize the class." is a fixed literal rather than derived
            # from humanize_identifier("__init__") == "init", which reads
            # worse than the boilerplate it would replace.
            generated = DocPart("Initialize the class.", Origin.FACT)
        else:
            # Derived from the function's name alone: true, but says little.
            generated = DocPart(
                humanize_identifier(func_node.name).capitalize() + ".", Origin.WEAK
            )
        parsed = parsed_info.get("summary")
        # A summary identical to the generated one is this tool's own output
        # from an earlier run, not the author's words.
        if parsed and parsed != generated.text:
            return DocPart(parsed, Origin.AUTHOR)
        return generated

    @staticmethod
    def _description_part(
        parsed_info: Dict[str, Any], summary: DocPart
    ) -> Optional[DocPart]:
        # A parsed description is the author's real words. Without one the
        # slot stays empty rather than holding a placeholder: a "nothing
        # to add" paragraph under a summary is noise, not honesty.
        description = parsed_info.get("description")
        if not description:
            return None
        if description.lower().rstrip(".") == summary.text.lower().rstrip("."):
            return None
        return DocPart(description, Origin.AUTHOR)

    def _arg_entries(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parsed_info: Dict[str, Any],
    ) -> list:
        # get_all_parameters() covers positional-only, positional-or-
        # keyword, *args, keyword-only, and **kwargs params -- the full
        # ast.arguments grammar, not just func_node.args.args.
        all_params = exclude_self_cls(get_all_parameters(func_node))
        sibling_params = [p.name for p in all_params]
        entries = []
        for param in all_params:
            # A real static type annotation is provably correct from the
            # code and always wins. Only fall back to a type documented in
            # an existing docstring when static inference has nothing to
            # offer ("any").
            static_type = self._infer_param_type(param)
            docstring_type = parsed_info.get("param_types", {}).get(param.display_name)
            inferred_type = (
                static_type if static_type != "any" else (docstring_type or static_type)
            )
            default_str = (
                self._get_default_value(param.default)
                if param.default is not None
                else None
            )
            entries.append(
                ArgEntry(
                    name=param.display_name,
                    display_type="Any" if inferred_type == "any" else inferred_type,
                    part=self._arg_part(
                        func_node, parsed_info, param, inferred_type, sibling_params
                    ),
                    default=default_str,
                )
            )
        return entries

    def _arg_part(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parsed_info: Dict[str, Any],
        param: Any,
        inferred_type: str,
        sibling_params: list,
    ) -> DocPart:
        # The rendered line always ends with " (default: ...)", so the
        # description itself never restates the default.
        desc = self._get_parameter_description(
            func_name=func_node.name,
            param_name=param.name,
            inferred_type=inferred_type,
            sibling_params=sibling_params,
        )
        generated = DocPart(
            desc,
            (
                Origin.GUESS
                if desc == GUESS_MARKER
                else Origin.FACT if has_name_signal(param.name) else Origin.WEAK
            ),
        )

        parsed_desc = parsed_info.get("params", {}).get(param.display_name)
        if not parsed_desc:
            return generated
        # A previous generation pass appended the " (default: ...)" suffix;
        # strip it so re-rendering doesn't compound it (see
        # _strip_own_default_annotation).
        parsed_desc = self._strip_own_default_annotation(parsed_desc)
        if self._is_own_output(parsed_desc, param, inferred_type, func_node):
            return generated
        return DocPart(parsed_desc, Origin.AUTHOR)

    def _is_own_output(
        self,
        text: str,
        param: Any,
        inferred_type: str,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    ) -> bool:
        """Whether a parsed parameter description is this tool's own output
        from an earlier run -- its guess marker, or the inferred text (in the
        current form, or the pre-2.6 form that also restated the default)
        -- rather than words an author wrote.

        Args:
            text (str): The parsed description, default suffix removed.
            param (Any): The parameter.
            inferred_type (str): Its type, as used for inference.
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.

        Returns:
            bool: ``True`` if the text should be regenerated, not kept.
        """
        if GUESS_MARKER in text:
            return True
        default_str = (
            self._get_default_value(param.default)
            if param.default is not None
            else None
        )
        own_forms = {
            self._get_parameter_description(
                func_name=func_node.name,
                param_name=param.name,
                inferred_type=inferred_type,
                default_value=default,
            )
            for default in (None, default_str)
        }
        return text in own_forms or text.rstrip(".") + "." in own_forms

    def _returns_entry(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parsed_info: Dict[str, Any],
    ) -> Optional[ReturnsEntry]:
        local_types = self._get_local_types(func_node)
        is_generator = self._is_generator(func_node)
        return_type = self._get_return_type(func_node, local_types)
        display_type = "Any" if return_type == "any" else return_type
        label = "Yields" if is_generator else "Returns"

        existing_desc = parsed_info.get("returns")
        if existing_desc and GUESS_MARKER in existing_desc:
            # The guess marker from an earlier run, not author text.
            existing_desc = None
        if existing_desc == "None.":
            # This tool's own literal for "no return value to describe",
            # not author text -- treated as absent so regeneration stays
            # stable and a function since edited to return something falls
            # through to a fresh entry below.
            existing_desc = None

        if existing_desc:
            return ReturnsEntry(
                label,
                display_type,
                DocPart(
                    self._strip_return_type_prefix(existing_desc, return_type),
                    Origin.AUTHOR,
                ),
            )
        if func_node.name == "__init__" and not is_generator:
            # Constructors implicitly return None; Google style omits
            # Returns rather than describing a value that's never returned.
            return None
        if return_type == "None":
            # No value returned anywhere in the body: nothing to describe.
            return ReturnsEntry(label, None, DocPart("None.", Origin.FACT))

        bool_desc = (
            describe_bool_return(func_node)
            if return_type == "bool" and not is_generator
            else None
        )
        if bool_desc:
            return ReturnsEntry(label, display_type, DocPart(bool_desc, Origin.FACT))
        return ReturnsEntry(label, display_type, DocPart(GUESS_MARKER, Origin.GUESS))

    @staticmethod
    def _strip_return_type_prefix(description: str, return_type: str) -> str:
        """Removes a leading "type:" from a parsed return description, so
        re-rendering it under the current type doesn't repeat the type."""
        if ":" not in description:
            return description
        prefix, rest = description.split(":", 1)
        prefix_clean = prefix.strip()
        if (
            prefix_clean == return_type
            or " " not in prefix_clean
            or "[" in prefix_clean
            or "|" in prefix_clean
        ):
            return rest.strip()
        return description

    def _generate_class_docstring(self, class_node: ast.ClassDef) -> str:
        """Generates a Google-style docstring for a class node, merging
        existing info."""
        existing_doc, prefix = None, ""
        try:
            existing_doc, prefix = self._existing_docstring(class_node)
            parser = DocstringParser(existing_doc)
            parsed_info = parser.get_info()

            summary = parsed_info.get("summary") or f"{class_node.name} class."
            # See the matching comment in _generate_function_docstring: a
            # parsed description wins outright, otherwise the slot stays
            # empty rather than duplicating the (possibly name-derived)
            # summary with a placeholder that adds no information.
            description = parsed_info.get("description") or ""

            docstring = f'"""{summary}\n\n'
            if description:
                docstring += f"{description}\n\n"

            attribute_lines = self._build_attribute_lines(class_node, parsed_info)
            if attribute_lines:
                docstring += "Attributes:\n" + "".join(attribute_lines)

            # Methods: is never generated: it isn't a standard Google-style
            # section, each public method carries its own docstring, and
            # nothing the AST knows fits in one line per method without
            # guessing. An author's own Methods: entries are kept.
            methods = self._carried_forward_methods(parsed_info.get("methods", ""))
            if methods:
                docstring += "\nMethods:\n" + methods + "\n"

            docstring += '"""'
            return prefix + docstring
        except Exception as e:
            logger.error(f"Error generating class docstring for {class_node.name}: {e}")
            if existing_doc is not None:
                # See the matching comment in _generate_function_docstring:
                # never let an unexpected failure silently discard a real,
                # existing docstring in favor of a placeholder.
                return f'{prefix}"""{existing_doc}"""'
            return '"""Error generating docstring."""'

    def _build_attribute_lines(
        self, class_node: ast.ClassDef, parsed_info: Dict[str, Any]
    ) -> list:
        """Builds the Attributes: entries, never discarding an author's.

        Detected attributes use the author's existing description when there
        is one, otherwise the same name/type inference Args: uses. Attributes
        the author documented but detection didn't find (class constants,
        properties) are kept as written.

        Args:
            class_node (ast.ClassDef): The class node.
            parsed_info (Dict[str, Any]): The existing docstring, parsed.

        Returns:
            list: One formatted, newline-terminated line per attribute.
        """
        documented = dict(parsed_info.get("attributes", {}))
        documented_types = parsed_info.get("attribute_types", {})
        lines = []
        for attr, attr_type in self._get_class_attributes(class_node).items():
            if attr_type == "any":
                attr_type = documented_types.get(attr, attr_type)
            author_desc = documented.pop(attr, None)
            desc = (
                author_desc
                if _is_carried_forward(author_desc)
                else self._get_parameter_description(
                    func_name=class_node.name,
                    param_name=attr,
                    inferred_type=attr_type,
                )
            )
            display_type = "Any" if attr_type == "any" else attr_type
            lines.append(f"    {attr} ({display_type}): {desc}\n")
        for attr, desc in documented.items():
            if not _is_carried_forward(desc):
                continue
            attr_type = documented_types.get(attr)
            type_part = f" ({attr_type})" if attr_type else ""
            lines.append(f"    {attr}{type_part}: {desc}\n")
        return lines

    @staticmethod
    def _carried_forward_methods(section_body: str) -> str:
        """An author's Methods: section, minus entries this tool generated.

        Entries are the least-indented lines; deeper lines continue the
        entry above them. An entry containing the guess marker came from an
        earlier run of this tool and is dropped along with its continuation.

        Args:
            section_body (str): The existing Methods: section body.

        Returns:
            str: The kept lines, re-indented under a Methods: header, or
                ``""`` if none remain.
        """
        lines = [line for line in section_body.splitlines() if line.strip()]
        if not lines:
            return ""
        base = min(len(line) - len(line.lstrip()) for line in lines)
        entries = []
        for line in lines:
            indent = len(line) - len(line.lstrip())
            if indent == base or not entries:
                entries.append([])
            entries[-1].append(" " * (4 + indent - base) + line.strip())
        kept = [
            line
            for entry in entries
            if _is_carried_forward(" ".join(entry))
            for line in entry
        ]
        return "\n".join(kept)

    def _get_parameter_description(
        self,
        func_name: str,
        param_name: str,
        inferred_type: str = None,
        default_value: str = None,
        sibling_params: list = None,
    ) -> str:
        """Retrieve a description for a parameter via rule‑based inference.

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
                # Same parameter-extraction primitive the Args section uses,
                # so positional-only/keyword-only/*args/**kwargs params are
                # picked up here too, and with the same (correctly inferred)
                # type instead of falling back to "any" via a self.x= scan.
                for param in exclude_self_cls(get_all_parameters(item)):
                    attributes[param.name] = self._infer_param_type(param)
                # walk_skipping_nested_classes (not ast.walk) so a
                # self.x = ... assignment inside a class nested within
                # __init__ isn't misattributed to *this* class -- it
                # belongs to the nested class's own instance, not this
                # one. Nested closures are still descended into: they
                # share this __init__'s own self.
                for node in walk_skipping_nested_classes(item):
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

    def _infer_param_type(self, param: Any) -> str:
        """
        Infers a parameter's type, same as ``_infer_type`` plus a
        *args/**kwargs fallback.

        A real static type annotation is always used when present.
        Otherwise, ``*args``/``**kwargs`` collect into a tuple/dict at
        runtime regardless of annotation, so that's used as the
        last-resort fact for them instead of leaving them as "any".

        Args:
            param (Any): A ``param_utils.Parameter`` (has ``.arg`` and
                ``.kind``).

        Returns:
            str: The inferred type.
        """
        static_type = self._infer_type(param.arg)
        if static_type == "any":
            if param.kind == "vararg":
                return "tuple"
            if param.kind == "kwarg":
                return "dict"
        return static_type

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
        # A signed numeric literal (e.g. -1) parses as UnaryOp(USub, Constant),
        # not a single Constant -- ast only folds the sign into the constant
        # for compile-time optimization, which doesn't apply to a default
        # value expression here.
        if (
            isinstance(default_node, ast.UnaryOp)
            and isinstance(default_node.op, (ast.USub, ast.UAdd))
            and isinstance(default_node.operand, ast.Constant)
            and isinstance(default_node.operand.value, (int, float, complex))
        ):
            sign = "-" if isinstance(default_node.op, ast.USub) else "+"
            return f"{sign}{default_node.operand.value!r}"
        return "unknown"

    def _strip_own_default_annotation(self, description: str) -> str:
        """Removes a trailing " (default: ...)" suffix from a re-parsed
        parameter description, unconditionally -- not only when it happens
        to match the parameter's *current* default.

        Generation always appends this exact suffix onto a param's
        description (see the append in the Args: loop), and that append
        always uses the parameter's current, real default -- so any prior
        suffix found here is always safe to discard regardless of what
        value it names. Re-parsing a previously-generated docstring stores
        the whole line -- suffix included -- as the parameter's "existing"
        description, since DocstringParser has no way to distinguish it
        from real author text.

        Matching only a suffix equal to the *current* default (an earlier
        version of this method) left a gap: editing a parameter's default
        in source between `generate` runs (e.g. ``0.1`` -> ``0.2``) left the
        stale ``" (default: 0.1)"`` suffix in place, since it no longer
        matched, and the append below still added a fresh ``" (default:
        0.2)"`` on top -- the same unbounded-compounding failure as a bare
        rerun, just triggered by a legitimate source edit instead.

        Args:
            description (str): The re-parsed, possibly suffix-carrying
                description.

        Returns:
            str: ``description`` with any trailing "(default: ...)" suffix
                removed, or unchanged if there is none.
        """
        return _TRAILING_DEFAULT_ANNOTATION_RE.sub("", description)

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
            for node in walk_own_scope(func_node)
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
                for node in walk_own_scope(func_node)
                if isinstance(node, (ast.Yield, ast.YieldFrom))
                and node.value is not None
            ]
        else:
            value_nodes = [
                node
                for node in walk_own_scope(func_node)
                if isinstance(node, ast.Return) and node.value is not None
            ]

        value_types = {
            self._infer_expr_type(node.value, local_types) for node in value_nodes
        }

        filtered_types = {t for t in value_types if t != "any"}
        if not filtered_types and value_types:
            return "any"
        return " | ".join(sorted(filtered_types)) if filtered_types else "None"

    def _get_raised_exceptions(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> list:
        """Collects the exception class names a function's own body raises.

        See ``code_facts.raise_sites`` for which raise statements count.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.

        Returns:
            list: Exception class names, in source order, de-duplicated.
        """
        return list(raise_sites(func_node))

    def _raises_entries(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        documented: Dict[str, str],
    ) -> list:
        """Builds the Raises: entries, never discarding an author's.

        Each exception the code raises is described, in order of preference,
        by the author's existing text, the condition read off the code
        (``code_facts.describe_raise_condition``), or the guess marker.
        Exceptions the author documented but the body doesn't raise directly
        -- typically ones propagated from a call -- are kept as written.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.
            documented (Dict[str, str]): The existing docstring's Raises
                entries, by exception name as the author wrote it.

        Returns:
            list: ``RaisesEntry`` items, code-raised exceptions first.
        """
        # An author may write `errors.ConfigError` for a bare
        # `raise ConfigError(...)`; both name the same exception.
        by_short_name = {
            name.split(".")[-1]: (name, desc) for name, desc in documented.items()
        }
        entries = []
        for exc_name, nodes in raise_sites(func_node).items():
            _, author_desc = by_short_name.pop(exc_name, (None, None))
            if _is_carried_forward(author_desc):
                part = DocPart(author_desc, Origin.AUTHOR)
            else:
                condition = describe_raise_condition(func_node, nodes)
                part = (
                    DocPart(condition, Origin.FACT)
                    if condition
                    else DocPart(f"{GUESS_MARKER} when this is raised.", Origin.GUESS)
                )
            entries.append(RaisesEntry(exc_name, part))
        entries.extend(
            RaisesEntry(name, DocPart(desc, Origin.AUTHOR))
            for name, desc in by_short_name.values()
            if _is_carried_forward(desc)
        )
        return entries

    def _build_function_context(
        self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> FunctionContext:
        """Gathers a function's AST-derived facts for a description provider.

        Reuses the same primitives Args:/Returns:/Raises: generation
        already calls, so a provider is grounded in exactly the facts this
        tool has already verified from the code -- never from the
        function's name alone.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The
                function node.

        Returns:
            FunctionContext: The gathered facts.
        """
        all_params = exclude_self_cls(get_all_parameters(func_node))
        parameters = [
            ParameterFact(
                name=param.display_name,
                type_hint=self._infer_param_type(param),
                default=(
                    self._get_default_value(param.default)
                    if param.default is not None
                    else None
                ),
            )
            for param in all_params
        ]
        local_types = self._get_local_types(func_node)
        source = ast.get_source_segment(self.code, func_node) or ""
        return FunctionContext(
            name=func_node.name,
            parameters=parameters,
            return_type=self._get_return_type(func_node, local_types),
            is_generator=self._is_generator(func_node),
            raised_exceptions=self._get_raised_exceptions(func_node),
            source=source,
        )

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
        self.module_docstring: Optional[str] = None

    def visit_Module(self, node):
        # Opt-in only -- see PyCodeCommenter.__init__'s docstring for why.
        # Unlike functions/classes, a module with an existing docstring is
        # never touched at all -- see _generate_module_docstring for why.
        # An empty module (no body at all, e.g. a blank or whitespace-only
        # file) has nothing to describe, so it's left alone too.
        if (
            self.commenter._include_module_docstrings
            and ast.get_docstring(node) is None
            and node.body
        ):
            self.module_docstring = self.commenter._generate_module_docstring(node)
        self.generic_visit(node)

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

    A module docstring is handled separately (``module_docstring``, applied
    in ``leave_Module``) rather than through the position-keyed ``edits``
    dict: ``ast.Module`` has no ``.lineno``/``.col_offset`` at all (unlike
    every other node this transformer handles), and there's always at most
    one module docstring, always at the very top of the file, so no
    position lookup is needed to place it.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, edits: Dict[Any, str], module_docstring: Optional[str] = None):
        self._edits = edits
        self._module_docstring = module_docstring

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

    def leave_Module(self, original_node, updated_node):
        if self._module_docstring is None:
            return updated_node

        doc_line = cst.SimpleStatementLine(
            body=[cst.Expr(value=cst.SimpleString(value=self._module_docstring))]
        )

        stmts = list(updated_node.body)
        if stmts and self._is_docstring_stmt(stmts[0]):
            # Defensive only: DocstringVisitor sets module_docstring solely
            # when ast.get_docstring() found none, so this should never
            # actually trigger -- mirrors _patch's own replace-or-insert
            # handling for consistency.
            stmts[0] = stmts[0].with_changes(
                body=[
                    stmts[0]
                    .body[0]
                    .with_changes(value=cst.SimpleString(value=self._module_docstring))
                ]
            )
        else:
            stmts.insert(0, doc_line)
        return updated_node.with_changes(body=stmts)
