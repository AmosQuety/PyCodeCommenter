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
    Parses existing docstrings in both Google and Sphinx styles.
    Extracts summary, description, parameters, and return information.
    """

    def __init__(self, docstring: Optional[str] = None):
        self.raw_docstring = docstring or ""
        self.summary = ""
        self.description = ""
        self.params = {} # type: Dict[str, str]
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
        
        # Determine if it's likely Google or Sphinx
        if ":param" in remaining_content or ":return" in remaining_content:
            self._parse_sphinx(remaining_content)
        else:
            self._parse_google(remaining_content)

    def _parse_sphinx(self, content: str) -> None:
        """Parses Sphinx style documentation (:param name: desc)."""
        desc_lines = []
        current_param = None
        
        for line in content.splitlines():
            line = line.strip()
            if not line: continue
            
            if line.startswith(':param'):
                match = re.match(r':param\s+(\w+):\s*(.*)', line)
                if match:
                    current_param = match.group(1)
                    self.params[current_param] = match.group(2).strip()
                continue
            
            if line.startswith(':return'):
                match = re.match(r':returns?:\s*(.*)', line)
                if match:
                    self.returns = match.group(1).strip()
                current_param = None
                continue
                
            if current_param and not line.startswith(':'):
                self.params[current_param] += " " + line
            elif not line.startswith(':'):
                desc_lines.append(line)
        
        self.description = " ".join(desc_lines).strip()

    def _parse_google(self, content: str) -> None:
        """Parses Google style documentation (Args:, Returns:)."""
        # Split by sections, allowing headers to be at the start or after a newline
        sections = re.split(r'(?m)^ *(Args|Returns|Attributes|Methods):$', content)
        
        # If the first part doesn't match a header, it's the description
        self.description = sections[0].strip()
        
        for i in range(1, len(sections), 2):
            header = sections[i]
            body = sections[i+1] if i+1 < len(sections) else ""
            
            if header == "Args":
                self._parse_google_args(body)
            elif header == "Returns":
                self.returns = body.strip()

    def _parse_google_args(self, body: str) -> None:
        """
        Helper to parse the Args section of a Google docstring.
        
        Args:
            body (str): The body of the Args section.
        """
        current_arg = None
        for line in body.splitlines():
            # Match "    name (type): desc" or "    name: desc"
            # Improved regex to handle various spacing and optional types more robustly
            match = re.match(r'^\s+(\w+)\s*(?:\(([^)]+)\))?\s*:\s*(.*)', line)
            if match:
                current_arg = match.group(1)
                self.params[current_arg] = match.group(3).strip()
            elif current_arg and line.startswith('        '): # Continuation line
                self.params[current_arg] += " " + line.strip()

    def get_info(self) -> Dict[str, Any]:
        """Returns the parsed information as a dictionary."""
        return {
            "summary": self.summary,
            "description": self.description,
            "params": self.params,
            "returns": self.returns
        }
