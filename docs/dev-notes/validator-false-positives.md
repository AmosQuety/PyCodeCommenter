# Tool findings triaged while documenting the package itself (pyOpenSci prep)

Running `generate`, `validate` and `coverage` on PyCodeCommenter's own source
for the pyOpenSci submission. Each entry says whether the finding was a real
documentation gap or a fault in the tool, and what was done about it.

Baseline (v2.6.0 + branch work): 239 errors, 190 warnings, 99 infos, 70.2%
docstring coverage.

## Validator false positives (fixed)

| Finding | Why it was wrong | Fix |
|---|---|---|
| "Function has return type hint 'None' but no Returns section" | A `-> None` function returns nothing; requiring a `Returns:` section only produced noise (96 of the baseline warnings carried a return hint, most of them `None`). | `validator.py` skips the check when the hint is `None`. Regression test `test_none_return_hint_needs_no_returns_section`. |
| "Function has Returns section but doesn't return a value" on `raise NotImplementedError` / `...` bodies | An abstract method documents what implementations return; the body of an abstract stub never returns. | `validator.py` `_is_abstract_stub` skips the check. Regression tests added. |
| "Placeholder text 'Description of' found" on prose such as "a description of this definition" | The placeholder check was a case-insensitive substring match, so it also matched inside ordinary sentences (and would match `HACK` inside "hackathon"). | Markers are matched as whole uppercase words; "Description of" only at the start of a line. Regression tests added. |

## Generator faults noticed (not yet fixed; listed for a decision)

| Behaviour | Where seen | Note |
|---|---|---|
| Existing hand-wrapped summary or parameter text is re-joined onto one line, which can exceed 88 columns and fail flake8 (E501). | `review_cli.py` | "Your text kept" is true of the words, not the line breaks. Rewrapped by hand. |
| Functions with no parameters get `Args:\n    None.` and `-> None` functions get `Returns:\n    None.` | `review_cli.py` | Boilerplate that says nothing. |
| `raise self._missing_sdk()` is written up as `Raises: _missing_sdk: If ImportError occurs.` -- the callee's name is read as an exception class. | `direct_providers.py` | Real generator bug; the correct class is what the helper returns (`ProviderUnavailable`). Fixed by hand in the docstring only. |
| A `Callable[[float], None]` attribute is described as `Optional[Callable[any, None]]`. | `direct_providers.py` | Type shown wrongly (lowercase `any`, list dropped). |
| Unannotated parameters and weak descriptions such as `String value.` / `int value.` are written as if informative. | `review_cli.py` | Tagged as guesses by the tool; replaced by hand. |

## Validator findings judged real (docstring fixed)

- "Function has no docstring" / "Parameter not documented" on private helpers:
  real gaps by the tool's own standard; documented.

## Open questions (not resolved)

- Prose that legitimately mentions the whole word "TODO" (for example
  describing the tool's own gap markers) is still flagged as a placeholder,
  because the marker word cannot be told from a leftover note. Worded around
  in the docstrings (`gap marker`) so far.

## Possible real bugs found (not fixed, docstring-only commits)

- `coverage.py` `CoverageAnalyzer.analyze_directory`: `except (SyntaxError,
  ValueError)` comes before `except UnicodeDecodeError`, and
  `UnicodeDecodeError` is a subclass of `ValueError`, so the encoding branch
  is unreachable and encoding failures are logged as "Error parsing".
