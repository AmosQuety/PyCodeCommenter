"""
Documentation coverage analysis module for PyCodeCommenter.

This module provides tools for analyzing documentation coverage across Python
files and projects. It calculates metrics for function and class documentation
and generates coverage reports.

Classes:
    FileCoverage: Coverage statistics for a single file
    ProjectCoverage: Coverage statistics for entire project
    CoverageAnalyzer: Analyzes documentation coverage for files or projects
"""
# coverage.py

import ast
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class FileCoverage:
    """Coverage statistics for a single file."""
    path: str
    total_functions: int = 0
    documented_functions: int = 0
    total_classes: int = 0
    documented_classes: int = 0
    
    @property
    def coverage_percentage(self) -> float:
        total = self.total_functions + self.total_classes
        documented = self.documented_functions + self.documented_classes
        return (documented / total * 100) if total > 0 else 0.0

@dataclass
class ProjectCoverage:
    """Coverage statistics for entire project."""
    files: Dict[str, FileCoverage] = field(default_factory=dict)
    
    @property
    def total_coverage(self) -> float:
        total_items = sum(f.total_functions + f.total_classes for f in self.files.values())
        documented = sum(f.documented_functions + f.documented_classes for f in self.files.values())
        return (documented / total_items * 100) if total_items > 0 else 0.0
    
    def print_report(self):
        """Print coverage report to console."""
        print("\n" + "="*80)
        print("DOCUMENTATION COVERAGE REPORT")
        print("="*80)
        
        for path, coverage in sorted(self.files.items()):
            status = "[OK]" if coverage.coverage_percentage == 100 else "[!!]"
            # Shorten path for display
            display_path = os.path.basename(path)
            print(f"{status} {display_path:50} {coverage.coverage_percentage:5.1f}%")
        
        print("-"*80)
        print(f"{'TOTAL':52} {self.total_coverage:5.1f}%")
        print("="*80)
    
    def to_json(self) -> dict:
        """Export as JSON."""
        return {
            "total_coverage": self.total_coverage,
            "files": {
                path: {
                    "coverage": cov.coverage_percentage,
                    "functions": f"{cov.documented_functions}/{cov.total_functions}",
                    "classes": f"{cov.documented_classes}/{cov.total_classes}"
                }
                for path, cov in self.files.items()
            }
        }

class CoverageAnalyzer:
    """Analyzes documentation coverage for files or projects."""
    
    def analyze_file(self, file_path: str) -> FileCoverage:
        """Analyze a single Python file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        coverage = FileCoverage(path=file_path)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                coverage.total_functions += 1
                if ast.get_docstring(node):
                    coverage.documented_functions += 1
            elif isinstance(node, ast.ClassDef):
                coverage.total_classes += 1
                if ast.get_docstring(node):
                    coverage.documented_classes += 1
        
        return coverage
    
    def analyze_directory(self, directory: str, exclude_patterns: List[str] = None) -> ProjectCoverage:
        """Analyze all Python files in a directory."""
        exclude_patterns = exclude_patterns or ['__pycache__', '.git', 'venv', 'tests', 'test_']
        project = ProjectCoverage()
        
        for py_file in Path(directory).rglob('*.py'):
            # Skip excluded paths
            if any(pattern in str(py_file) for pattern in exclude_patterns):
                continue
            
            try:
                coverage = self.analyze_file(str(py_file))
                project.files[str(py_file)] = coverage
            except (IOError, OSError) as e:
                logger.error(f"Error reading {py_file}: {e}")
            except (SyntaxError, ValueError) as e:
                logger.error(f"Error parsing {py_file}: {e}")
            except UnicodeDecodeError as e:
                logger.error(f"Encoding error in {py_file}: {e}")
        
        return project
