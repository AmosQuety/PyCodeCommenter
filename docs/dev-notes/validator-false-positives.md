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

## Generator faults noticed (not yet fixed; listed for a decision)

| Behaviour | Where seen | Note |
|---|---|---|
| Existing hand-wrapped summary or parameter text is re-joined onto one line, which can exceed 88 columns and fail flake8 (E501). | `review_cli.py` | "Your text kept" is true of the words, not the line breaks. Rewrapped by hand. |
| Functions with no parameters get `Args:\n    None.` and `-> None` functions get `Returns:\n    None.` | `review_cli.py` | Boilerplate that says nothing. |
| Unannotated parameters and weak descriptions such as `String value.` / `int value.` are written as if informative. | `review_cli.py` | Tagged as guesses by the tool; replaced by hand. |

## Validator findings judged real (docstring fixed)

- "Function has no docstring" / "Parameter not documented" on private helpers:
  real gaps by the tool's own standard; documented.

## Open questions (not resolved)

- The placeholder check is a case-insensitive substring match, so prose that
  legitimately mentions the word "TODO" (for example describing a `TODO`
  review kind) is flagged. Worded around in the docstrings so far.
