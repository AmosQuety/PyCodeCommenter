# 🎯 Feature Improvement: Recursive Directory Support with Smart File Filtering

## Current Behavior
Currently, **PyCodeCommenter** is limited by the following constraints:
* **Single File Support Only:** Accepts only individual file paths.
* **Error Prone:** Fails with `[Errno 21] Is a directory` when passed a folder.
* **No Recursion:** Cannot traverse nested directory structures.
* **Manual Effort:** Users must manually exclude non-code files, virtual environments, and configuration folders.

---

## Proposed Enhancement
### Problem Statement
PyCodeCommenter is impractical for real-world projects with multiple files and complex folder structures. Users are forced to write external shell scripts or manually loop through files. Furthermore, there is no native way to ignore clutter like `.venv`, `__pycache__`, or `.git` directories.

### Proposed Solution
Add native support for directory paths with the following capabilities:
1. **Recursive Processing:** Automatically find all Python files within a tree.
2. **Intelligent Filtering:** Automatically skip non-code files and common environment folders.
3. **Custom Exclusions:** Respect `exclude` patterns defined in a configuration file.
4. **Rich Feedback:** Provide a progress UI and a detailed summary report.

---

## Implementation Details

### 1. Path Detection & File Collection
We will use `pathlib` for robust path handling and `os.walk` for traversal.

```python
from pathlib import Path
import os

# Default patterns to always skip
DEFAULT_IGNORE_PATTERNS = {
    '.venv', 'venv', 'env', 'ENV', 'virtualenv',
    '__pycache__', '*.pyc', '*.pyo', '*.pyd',
    '.git', '.svn', '.hg',
    '.vscode', '.idea', '.pycharm',
    'build', 'dist', '.eggs', '*.egg-info',
    'node_modules', 'package-lock.json', 'yarn.lock',
    '.DS_Store', 'Thumbs.db',
    '*.config', '*.ini', '*.toml', '*.yaml', '*.yml',
    '*.json', '*.xml', '*.cfg',
    'docs', '*.md', '*.rst', '*.txt',
    'tests', 'test_*', '*_test.py',
}

def should_skip_path(path, exclude_patterns=None):
    """Determine if a path should be skipped based on defaults and custom patterns."""
    path_parts = Path(path).parts
    
    # Check default patterns
    for pattern in DEFAULT_IGNORE_PATTERNS:
        if pattern.startswith('*.'):
            if Path(path).suffix == pattern[1:]:
                return True
        elif pattern in path_parts:
            return True
    
    # Check custom exclude patterns from config
    if exclude_patterns:
        for pattern in exclude_patterns:
            if pattern.startswith('*.'):
                if Path(path).suffix == pattern[1:]: return True
            elif pattern.startswith('**/') and pattern[3:] in str(path):
                return True
            elif pattern in path_parts:
                return True
    return False

def collect_py_files(path, exclude_patterns=None):
    """Recursively collect Python files, skipping ignored directories."""
    if os.path.isfile(path):
        return [path] if path.endswith('.py') else []
    
    py_files = []
    for root, dirs, files in os.walk(path):
        # Filter directories in-place to prevent walking into skipped folders
        dirs[:] = [d for d in dirs if not should_skip_path(os.path.join(root, d), exclude_patterns)]
        
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                if not should_skip_path(full_path, exclude_patterns):
                    py_files.append(full_path)
    return py_files
```

### 2. Processing Strategy & Summary
```python
def process_directory(path, dry_run=False, inplace=False, exclude_patterns=None):
    py_files = collect_py_files(path, exclude_patterns)
    
    if not py_files:
        print(f"❌ No Python files found in {path}")
        return

    print(f"📁 Found {len(py_files)} Python files in {path}\n")
    
    stats = {"modified": 0, "unchanged": 0, "failed": 0, "total_added": 0}
    
    for idx, file_path in enumerate(py_files, 1):
        display_path = Path(file_path).relative_to(path) if path != '.' else Path(file_path).name
        print(f"Processing {idx}/{len(py_files)}: {display_path} ... ", end='')
        
        try:
            result = generate_docstring(file_path, inplace=inplace, dry_run=dry_run)
            if result.added_count > 0:
                print(f"✅ (+{result.added_count} docstrings)")
                stats["modified"] += 1
                stats["total_added"] += result.added_count
            else:
                print(f"⚠️  (no changes needed)")
                stats["unchanged"] += 1
        except Exception as e:
            print(f"❌ (Error: {str(e)})")
            stats["failed"] += 1
    
    # Final Report Output...
```

### 3. Configuration File Enhancement (`.pycodecommenter.yaml`)
```yaml
exclude:
  - "tests/*"
  - "*/migrations/*"
  - "**/__pycache__/*"
  - "*.test.py"
  
use_gitignore: true

skip_extensions:
  - ".txt"
  - ".md"
  - ".json"
  - ".yaml"

skip_dirs:
  - ".venv"
  - "node_modules"
  - "build"
  - "docs"
```

---

## Example User Experience

### ❌ Before (Current)
```bash
$ pycodecommenter generate ./PyCodeCommenter/ --dry-run
Error reading file: [Errno 21] Is a directory: './PyCodeCommenter/'
Error: Could not parse ./PyCodeCommenter/
```

### ✅ After (Enhanced)
```bash
$ pycodecommenter generate ./PyCodeCommenter/ --dry-run
📁 Found 12 Python files in ./PyCodeCommenter/
📂 Skipped: .venv/, __pycache__/, .git/, docs/
📄 Skipped: config.json, *.md, *.yaml

Processing 1/12: __init__.py ... ✅ (+2 docstrings)
Processing 2/12: commenter.py ... ✅ (+3 docstrings)
...
Processing 10/12: tests/test_commenter.py ... ⏭️ (skipped - excluded)

================================================================
📊 Summary Report
================================================================
✅ Files modified:  7
⚠️  Files unchanged: 3
⏭️  Files skipped:   1
❌ Files failed:    1
📝 New docstrings:  21
📁 Total files:     11
```

---

## Implementation Roadmap

*   **Phase 1:** Basic recursive directory support with hardcoded skip patterns.
*   **Phase 2:** Progress reporting, summary statistics, and error handling.
*   **Phase 3:** Integration of `.pycodecommenter.yaml` and `.gitignore` support.
*   **Phase 4:** Performance optimization via parallel processing for large projects.
*   **Phase 5:** Interactive mode (selective file processing).

---

## Testing Strategy
| Scenario | Expected Behavior |
| :--- | :--- |
| **Empty Directory** | Graceful "No files found" message. |
| **Deep Nesting** | Traverse 10+ levels without stack overflow. |
| **Mixed File Types** | Filter out `.js`, `.md`, `.json`, etc. |
| **Virtual Envs** | Automatically detect and skip `.venv/` or `env/`. |
| **Invalid Syntax** | Log error for that specific file and continue to the next. |
| **Permissions** | Skip files with "Permission Denied" and log as failed. |

---

## Edge Case Handling
*   **Broken Symlinks:** Skip with a warning.
*   **Large Projects:** Use streaming output and efficient memory management.
*   **Cross-Platform:** Normalize paths for Windows and Linux compatibility.
*   **Recursion Limits:** Configurable max depth to prevent infinite loops on circular symlinks.