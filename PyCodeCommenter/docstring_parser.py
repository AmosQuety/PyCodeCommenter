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
from typing import Dict, Any, List, Optional

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
        r"(?m)^[ \t]*(Parameters|Returns|Raises)[ \t]*\r?\n[ \t]*-{3,}[ \t]*\r?\n?"
    )
    _NUMPY_DECL_RE = re.compile(r"^(\S.*?)\s*:\s*(.*)$")
    _TRAILING_OPTIONAL_RE = re.compile(r",?\s*optional\s*$", re.IGNORECASE)

    def __init__(self, docstring: Optional[str] = None):
        self.raw_docstring = docstring or ""
        self.summary = ""
        self.description = ""
        self.params = {}  # type: Dict[str, str]
        self.param_types = {}  # type: Dict[str, str]
        self.returns = ""

        if self.raw_docstring:
            self.parse()

    def parse(self) -> None:
        """Main entry point for parsing the docstring."""
        if not self.raw_docstring.strip():
            return

        lines = self.raw_docstring.strip().splitlines()
        self.summary = lines[0].strip()

        remaining_content = "\n".join(lines[1:]).strip()

        # Determine the style: NumPy's dash-underlined headers are checked
        # first since they're the most specific signature and can't be
        # produced by Google or Sphinx style.
        if self._NUMPY_HEADER_RE.search(remaining_content):
            self._parse_numpy(remaining_content)
        elif ":param" in remaining_content or ":return" in remaining_content:
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

            if line.startswith(":return"):
                match = re.match(r":returns?:\s*(.*)", line)
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
            r"(?m)^ *(Args|Returns|Yields|Attributes|Methods):$", content
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
                self._parse_numpy_params(body)
            elif header == "Returns":
                self._parse_numpy_returns(body)
            elif header == "Raises":
                # No first-class "raises" field exists in this data model,
                # and nothing downstream regenerates a Raises section, so
                # fold it into the description rather than dropping it -
                # non-lossy, and it can't collide/duplicate later.
                if body.strip():
                    self.description = (
                        self.description + "\n\nRaises\n" + body.strip()
                    ).strip()

    def _parse_numpy_params(self, body: str) -> None:
        """Helper to parse a NumPy-style Parameters section.

        Declaration lines (e.g. "name : type" or "name1, name2 : type",
        NumPy's shared-type convention for multiple parameters) sit at
        column 0; indented lines are the continuation of the current
        name(s)' description.

        Args:
            body (str): The body of the Parameters section.
        """
        current_names = []
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
                    self.params[name] = ""
                    if type_part:
                        self.param_types[name] = type_part
            elif current_names:
                piece = line.strip()
                for name in current_names:
                    self.params[name] = (self.params[name] + " " + piece).strip()

    def _parse_numpy_returns(self, body: str) -> None:
        """Helper to parse a NumPy-style Returns section (bare "type" or
        "name : type" on the first line, followed by an indented
        description).

        Args:
            body (str): The body of the Returns section.
        """
        lines = [l for l in body.splitlines() if l.strip()]
        if not lines:
            return
        header_line = lines[0].strip()
        desc = " ".join(l.strip() for l in lines[1:])
        self.returns = f"{header_line}: {desc}".strip() if desc else header_line

    def get_info(self) -> Dict[str, Any]:
        """Returns the parsed information as a dictionary."""
        return {
            "summary": self.summary,
            "description": self.description,
            "params": self.params,
            "param_types": self.param_types,
            "returns": self.returns,
        }
