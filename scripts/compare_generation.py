"""Compare docstring generation between two versions of PyCodeCommenter.

Runs each version over the same corpus of Python files and reports, per
version: TODO markers left, validator issues on the generated output,
generated Methods: sections, files whose output doesn't parse, files that
change on a second run (not idempotent), and files whose *code* (not
docstrings) changed. Run it before and after any change to the generator;
"broken output" and "code changed" must stay at 0, and "not idempotent"
should too.

This is how a real regression was caught in v2.6.0: the old code turned an
escaped \\"\\"\\" inside a docstring into a real triple quote and wrote out
a file that no longer parsed.

Usage:
    # Export the old version somewhere (it needs no install):
    git archive <old-commit> | tar -x -C /tmp/old
    python scripts/compare_generation.py /tmp/old . path/to/corpus/

The corpus is any directory of .py files -- this package's own modules,
tests/fixtures/docstring_generation_fixture.py, and a few real projects make a
good one. Nothing is sent anywhere: AI drafting is not used.
"""

import ast
import collections
import importlib
import logging
import pathlib
import sys

logging.disable(logging.CRITICAL)


def load_commenter(root: str):
    """Imports PyCodeCommenter from a given source tree, isolated from any
    previously imported version."""
    for name in [m for m in sys.modules if m.split(".")[0] == "PyCodeCommenter"]:
        del sys.modules[name]
    sys.path.insert(0, root)
    try:
        return importlib.import_module("PyCodeCommenter").PyCodeCommenter
    finally:
        sys.path.pop(0)


def code_without_docstrings(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def measure(commenter_cls, corpus: pathlib.Path) -> collections.Counter:
    totals = collections.Counter()
    for path in sorted(corpus.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        output = commenter_cls().from_string(source).get_patched_code()
        totals["files"] += 1
        totals["TODO markers"] += output.count("TODO(pycodecommenter)")
        totals["Methods: sections"] += output.count("Methods:")
        try:
            changed = code_without_docstrings(source) != code_without_docstrings(output)
        except SyntaxError:
            totals["BROKEN output files"] += 1
            print(f"  broken output: {path}")
            continue
        totals["code changed (must be 0)"] += changed
        again = commenter_cls().from_string(output).get_patched_code()
        totals["not idempotent"] += again != output
        report = commenter_cls().from_string(output).validate()
        for issue in report.issues:
            totals[f"validator: {issue.category}"] += 1
    return totals


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    old_root, new_root, corpus = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    old = measure(load_commenter(old_root), corpus)
    new = measure(load_commenter(new_root), corpus)
    print(f"{'':32}{'old':>8}{'new':>8}")
    for key in sorted(set(old) | set(new)):
        print(f"{key:32}{old[key]:>8}{new[key]:>8}")


if __name__ == "__main__":
    main()
