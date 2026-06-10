# Configuration Reference

PyCodeCommenter can be configured with a YAML file that is discovered automatically by walking up the directory tree from wherever you run the tool.

> **Important:** As of version 2.1.0, the configuration file is **loaded** but its keys are not yet consumed by the CLI or the core generation/validation logic. The `load_config()` function and `ConfigError` exception are part of the public API and are ready for programmatic use. Several keys documented in the README (such as `style`, `validation.level`, and `coverage.threshold`) are present in the README example but are not yet wired into any runtime behaviour. This page is honest about that distinction.

---

## How Config is Discovered

The config loader walks **up** the directory tree starting from `start_path` (which defaults to the current working directory) until it finds a file named `.pycodecommenter.yaml` or reaches the filesystem root.

From `config.py`:

```python
def _find_config_path(start_path=None):
    if start_path is None:
        start_path = os.getcwd()
    current = Path(start_path).resolve()
    while True:
        candidate = current / ".pycodecommenter.yaml"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None          # Reached filesystem root, file not found
        current = current.parent
```

In practice this means:
- If you run `pycodecommenter generate src/api.py` from `/home/user/myproject`, the loader checks `/home/user/myproject/.pycodecommenter.yaml`, then `/home/user/.pycodecommenter.yaml`, then `/home/.pycodecommenter.yaml`, and so on.
- The **first** file found wins.
- If no file is found, an **empty dict** is returned and the tool runs with built-in defaults.

---

## Loading Config Programmatically

```python
from PyCodeCommenter.config import load_config, ConfigError

try:
    config = load_config()            # Searches from cwd
    config = load_config("/my/dir")   # Searches from a specific path
except ConfigError as e:
    print(f"Bad config: {e}")
```

`ConfigError` is raised only when a `.pycodecommenter.yaml` file is **found** but **cannot be parsed**. A missing file is not an error.

---

## Config File Format

The file must be valid YAML and is parsed with `ruamel.yaml` in safe mode.

Create `.pycodecommenter.yaml` in your project root:

```yaml
# .pycodecommenter.yaml
# All keys shown with their README-documented values.
# See the "Key Status" column in the table below for what is actually active.

style: google

validation:
  level: strict
  check_types: true
  check_exceptions: true

coverage:
  threshold: 80
  fail_below: true

exclude:
  - "*/tests/*"
  - "*/migrations/*"
  - "*/__pycache__/*"
```

---

## Key Reference

| Key | Type | README Default | Status | Description |
|-----|------|----------------|--------|-------------|
| `style` | `string` | `"google"` | **Not yet implemented** | Intended output docstring style. Only Google style is currently generated regardless of this value |
| `validation.level` | `string` | `"strict"` | **Not yet implemented** | Intended validation strictness. The validator always runs all six checks |
| `validation.check_types` | `bool` | `true` | **Not yet implemented** | Intended to toggle type-consistency checks |
| `validation.check_exceptions` | `bool` | `true` | **Not yet implemented** | Intended to toggle exception-documentation checks |
| `coverage.threshold` | `number` | `80` | **Not yet implemented** | Intended minimum coverage percentage for CI gating |
| `coverage.fail_below` | `bool` | `true` | **Not yet implemented** | Intended to control whether failing the threshold causes a non-zero exit |
| `exclude` | `list of strings` | `[]` | **Not yet implemented** — CLI `--exclude` works independently | Intended to be the persistent exclude list for `coverage` and `validate` commands |

> All keys load cleanly via `load_config()` and are returned in the dictionary, but nothing in the CLI or core classes reads them at runtime yet. They are planned for a future release.

---

## Per-project vs Global Config

Because the search walks **up** from the current directory:

- **Project-level config**: Place `.pycodecommenter.yaml` in the root of your repository. Running `pycodecommenter` from any subdirectory of that repo will find it.
- **User-level config**: Place `.pycodecommenter.yaml` in your home directory (`~/.pycodecommenter.yaml`). It will be found for any project that doesn't have its own config file.
- **No config**: If no file exists anywhere up the tree, an empty dict is returned and built-in defaults apply.

---

## Dependency

Config loading requires `ruamel.yaml >= 0.17`, which is declared as a runtime dependency in `pyproject.toml` and is installed automatically with `pip install pycodecommenter`.

---

## Related

- **[CLI Reference](cli-reference.md)** — current CLI flags for `--exclude` (works independently of the config file)
- **[Recipes](recipes.md)** — project setup examples
- **[FAQ](faq.md)** — questions about config support
