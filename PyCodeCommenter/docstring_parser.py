"""
Docstring parsing module for PyCodeCommenter.

This module provides intelligent parsing of existing Python docstrings in multiple
formats (Google, Sphinx, NumPy). It extracts structured information including
summary, description, parameters, and return values for smart docstring merging.

Classes:
    DocstringParser: Main parser class for extracting docstring information
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DocstringParser:
    """
    Parses existing docstrings in Google, Sphinx, and NumPy styles.
    Extracts summary, description, parameters (with types), and return
    information.
    """

    # A NumPy-style section header (Parameters/Returns/Raises) immediately
    # followed by a dash underline. This signature is unambiguous - neither
    # Google style (`Args:` on one line) nor Sphinx style (`:param:`) can
    # produce it - so it's checked first in parse().
    _NUMPY_HEADER_RE = re.compile(
        r"(?m)^[ \t]*(Parameters|Returns|Yields|Raises|Attributes)[ \t]*\r?\n"
        r"[ \t]*-{3,}[ \t]*\r?\n?"
    )
    _NUMPY_DECL_RE = re.compile(r"^(\S.*?)\s*:\s*(.*)$")
    _TRAILING_OPTIONAL_RE = re.compile(r",?\s*optional\s*$", re.IGNORECASE)

    # Boundaries that end the summary paragraph when scanning forward from
    # the second physical line: a blank line, or a line that is itself a
    # recognized section header (so a summary immediately followed by
    # Args:/etc with no blank line doesn't swallow the header into the
    # summary text).
    _GOOGLE_HEADER_RE = re.compile(
        r"^\s*(Args|Returns|Yields|Raises|Attributes|Methods):\s*$"
    )
    _SPHINX_FIELD_RE = re.compile(
        r"^\s*:(param|type|returns?|rtype|raises?|yields?|ivar|vartype)\b"
    )

    # One "name (type): description" entry in a Google-style Raises: or
    # Attributes: section. The name may be dotted (`errors.ConfigError`).
    _GOOGLE_ENTRY_RE = re.compile(r"^(\s+)([\w.]+)\s*(?:\(([^)]+)\))?\s*:\s*(.*)$")

    def __init__(self, docstring: Optional[str] = None):
        self.raw_docstring = docstring or ""
        # "google", "numpy" or "sphinx": the style an existing docstring is
        # written in, so regeneration can keep it. A docstring with no
        # sections (or none at all) counts as Google, the default.
        self.style = "google"
        self.summary = ""
        self.description = ""
        self.params = {}  # type: Dict[str, str]
        self.param_types = {}  # type: Dict[str, str]
        self.returns = ""
        self.raises = {}  # type: Dict[str, str]
        self.attributes = {}  # type: Dict[str, str]
        self.attribute_types = {}  # type: Dict[str, str]
        # Kept verbatim: Methods: is not a section the generator produces,
        # so there is nothing to merge -- only author text to carry forward.
        self.methods = ""

        if self.raw_docstring:
            self.parse()

    def parse(self) -> None:
        """Main entry point for parsing the docstring."""
        if not self.raw_docstring.strip():
            return

        lines = self.raw_docstring.strip().splitlines()

        # The summary is the docstring's first paragraph, not just its
        # first physical line: a hand-wrapped sentence spanning several
        # physical lines with no blank line between them is one summary,
        # not a summary followed by a spurious description fragment
        # starting mid-sentence. A docstring that starts directly with a
        # section header (no summary text at all, e.g. a stray blank line
        # swallowed by the .strip() above) has an empty summary rather than
        # the header line itself.
        if self._GOOGLE_HEADER_RE.match(lines[0]) or self._SPHINX_FIELD_RE.match(
            lines[0]
        ):
            summary_end = 0
        else:
            summary_end = len(lines)
            for i, line in enumerate(lines[1:], start=1):
                if (
                    not line.strip()
                    or self._GOOGLE_HEADER_RE.match(line)
                    or self._SPHINX_FIELD_RE.match(line)
                ):
                    summary_end = i
                    break

        self.summary = " ".join(line.strip() for line in lines[:summary_end])
        remaining_content = "\n".join(lines[summary_end:]).strip()

        # Determine the style: NumPy's dash-underlined headers are checked
        # first since they're the most specific signature and can't be
        # produced by Google or Sphinx style.
        if self._NUMPY_HEADER_RE.search(remaining_content):
            self.style = "numpy"
            self._parse_numpy(remaining_content)
        elif any(
            self._SPHINX_FIELD_RE.match(ln) for ln in remaining_content.splitlines()
        ):
            self.style = "sphinx"
            self._parse_sphinx(remaining_content)
        else:
            self._parse_google(remaining_content)

    def _parse_sphinx(self, content: str) -> None:
        """Parses Sphinx style documentation (:param name: desc)."""
        desc_lines = []
        current_param = None

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith(":param"):
                match = re.match(r":param\s+(\w+):\s*(.*)", line)
                if match:
                    current_param = match.group(1)
                    self.params[current_param] = match.group(2).strip()
                continue

            if line.startswith(":type"):
                match = re.match(r":type\s+(\w+):\s*(.*)", line)
                if match:
                    self.param_types[match.group(1)] = match.group(2).strip()
                continue

            if line.startswith(":raise"):
                match = re.match(r":raises?\s+([\w.]+):\s*(.*)", line)
                if match:
                    self.raises[match.group(1)] = match.group(2).strip()
                current_param = None
                continue

            if line.startswith(":ivar") or line.startswith(":vartype"):
                match = re.match(r":(ivar|vartype)\s+(\w+):\s*(.*)", line)
                if match:
                    target = (
                        self.attributes
                        if match.group(1) == "ivar"
                        else (self.attribute_types)
                    )
                    target[match.group(2)] = match.group(3).strip()
                current_param = None
                continue

            if line.startswith(":return") or line.startswith(":yield"):
                # Like Google style, Yields shares the returns slot.
                match = re.match(r":(?:returns?|yields?):\s*(.*)", line)
                if match:
                    self.returns = match.group(1).strip()
                current_param = None
                continue

            if current_param and not line.startswith(":"):
                self.params[current_param] += " " + line
            elif not line.startswith(":"):
                desc_lines.append(line)

        self.description = " ".join(desc_lines).strip()

    def _parse_google(self, content: str) -> None:
        """Parses Google style documentation (Args:, Returns:, Yields:)."""
        # Split by sections, allowing headers to be at the start or after a newline
        sections = re.split(
            r"(?m)^ *(Args|Returns|Yields|Raises|Attributes|Methods):$", content
        )

        # If the first part doesn't match a header, it's the description
        self.description = sections[0].strip()

        for i in range(1, len(sections), 2):
            header = sections[i]
            body = sections[i + 1] if i + 1 < len(sections) else ""

            if header == "Args":
                self._parse_google_args(body)
            elif header in ("Returns", "Yields"):
                # Yields shares the same "returns" slot -- both describe
                # what comes back out of the function, just via a different
                # mechanism (a generator's Yields section vs. a plain
                # return), and nothing downstream needs to distinguish them
                # when merging.
                self.returns = body.strip()
            elif header == "Raises":
                self.raises, _ = self._parse_google_entries(body)
            elif header == "Attributes":
                self.attributes, self.attribute_types = self._parse_google_entries(body)
            elif header == "Methods":
                self.methods = body.strip("\n").rstrip()

    def _parse_google_entries(self, body: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Parses the "name (type): description" entries of a Google-style
        Raises: or Attributes: section.

        A line indented deeper than the entries continues the current
        entry's description; a line at or above the section's own
        indentation that isn't an entry (e.g. a following ``Note:`` header)
        ends it, rather than being glued onto the last description.

        Args:
            body (str): The section body, below its header line.

        Returns:
            Tuple[Dict[str, str], Dict[str, str]]: Descriptions by name, and
                the types of the entries that declared one.
        """
        descriptions: Dict[str, str] = {}
        types: Dict[str, str] = {}
        entry_indent = None
        current = None
        for line in body.splitlines():
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            match = self._GOOGLE_ENTRY_RE.match(line)
            if match and (entry_indent is None or indent <= entry_indent):
                entry_indent = indent
                current = match.group(2)
                descriptions[current] = match.group(4).strip()
                if match.group(3):
                    types[current] = match.group(3).strip()
            elif current is not None and indent > entry_indent:
                descriptions[current] = (
                    f"{descriptions[current]} {line.strip()}".strip()
                )
            else:
                current = None
        return descriptions, types

    def _parse_google_args(self, body: str) -> None:
        """
        Helper to parse the Args section of a Google docstring.

        Args:
            body (str): The body of the Args section.
        """
        current_arg = None
        for line in body.splitlines():
            # Match "    name (type): desc", "    name: desc", or the
            # "*args"/"**kwargs" star-prefixed form.
            # Improved regex to handle various spacing and optional types more robustly
            match = re.match(r"^\s+(\*{0,2}\w+)\s*(?:\(([^)]+)\))?\s*:\s*(.*)", line)
            if match:
                current_arg = match.group(1)
                self.params[current_arg] = match.group(3).strip()
                if match.group(2):
                    self.param_types[current_arg] = match.group(2).strip()
            elif current_arg and line.strip():  # Continuation line, any indentation
                self.params[current_arg] += " " + line.strip()

    def _parse_numpy(self, content: str) -> None:
        """Parses NumPy style documentation (Parameters/Returns/Raises
        sections underlined with dashes)."""
        parts = self._NUMPY_HEADER_RE.split(content)
        self.description = parts[0].strip()

        for i in range(1, len(parts), 2):
            header = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""

            if header == "Parameters":
                self.params, self.param_types = self._parse_numpy_entries(body)
            elif header == "Attributes":
                self.attributes, self.attribute_types = self._parse_numpy_entries(body)
            elif header in ("Returns", "Yields"):
                self._parse_numpy_returns(body)
            elif header == "Raises":
                # Parsed into `raises`, never folded into `description`:
                # that used to leave a malformed NumPy block floating above
                # Args: alongside the generated Google-style Raises: section.
                self._parse_numpy_raises(body)

    def _parse_numpy_entries(self, body: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Parses a NumPy-style Parameters or Attributes section.

        Declaration lines (e.g. "name : type" or "name1, name2 : type",
        NumPy's shared-type convention for several names) sit at column 0;
        indented lines continue the current name(s)' description. A
        trailing ", optional" on the type is dropped.

        Args:
            body (str): The section body, below its underline.

        Returns:
            Tuple[Dict[str, str], Dict[str, str]]: Descriptions by name, and
                the types of the entries that declared one.
        """
        descriptions: Dict[str, str] = {}
        types: Dict[str, str] = {}
        current_names: List[str] = []
        for line in body.splitlines():
            if not line.strip():
                continue
            if line[:1] not in (" ", "\t"):
                match = self._NUMPY_DECL_RE.match(line)
                if match:
                    names_part, type_part = match.group(1), match.group(2).strip()
                else:
                    names_part, type_part = line.strip(), ""
                current_names = [n.strip() for n in names_part.split(",") if n.strip()]
                type_part = self._TRAILING_OPTIONAL_RE.sub("", type_part).strip()
                for name in current_names:
                    descriptions[name] = ""
                    if type_part:
                        types[name] = type_part
            elif current_names:
                piece = line.strip()
                for name in current_names:
                    descriptions[name] = (descriptions[name] + " " + piece).strip()
        return descriptions, types

    def _parse_numpy_raises(self, body: str) -> None:
        """Helper to parse a NumPy-style Raises section: an exception name
        at column 0, followed by its indented description.

        Args:
            body (str): The body of the Raises section.
        """
        current = None
        for line in body.splitlines():
            if not line.strip():
                continue
            if line[:1] not in (" ", "\t"):
                current = line.strip()
                self.raises[current] = ""
            elif current is not None:
                self.raises[current] = f"{self.raises[current]} {line.strip()}".strip()

    def _parse_numpy_returns(self, body: str) -> None:
        """Helper to parse a NumPy-style Returns section (bare "type" or
        "name : type" on the first line, followed by an indented
        description).

        Args:
            body (str): The body of the Returns section.
        """
        lines = [ln for ln in body.splitlines() if ln.strip()]
        if not lines:
            return
        header_line = lines[0].strip()
        desc = " ".join(ln.strip() for ln in lines[1:])
        self.returns = f"{header_line}: {desc}".strip() if desc else header_line

    def get_info(self) -> Dict[str, Any]:
        """Returns the parsed information as a dictionary."""
        return {
            "summary": self.summary,
            "description": self.description,
            "params": self.params,
            "param_types": self.param_types,
            "returns": self.returns,
            "raises": self.raises,
            "attributes": self.attributes,
            "attribute_types": self.attribute_types,
            "methods": self.methods,
            "style": self.style,
        }
