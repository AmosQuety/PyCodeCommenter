# Changelog

All notable changes to PyCodeCommenter will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

Follow-up work from a dogfooding audit run against the tool's own codebase
(`Another_Test_PyCodeCommenter/Feedback/AUDIT_REPORT.md`) — every numbered
finding in that audit is now closed; see `Future Work/Audit Remediation
Log.md` for the full history.

### Changed
- **NumPy- and Sphinx-style docstrings keep their style.** Regenerating
  used to convert them to Google style. Now gaps are filled in the
  docstring's own convention -- NumPy's dash-underlined `Parameters`/
  `Returns`/`Yields`/`Raises`/`Attributes` sections, or Sphinx's
  `:param:`/`:type:`/`:returns:`/`:rtype:`/`:raises:`/`:ivar:` fields --
  and new docstrings are still Google style. The parser now also reads
  NumPy `Yields`/`Attributes` and Sphinx `:yields:`/`:ivar:`/`:vartype:`,
  which were previously dropped.

### Added
- **`pycodecommenter review`** steps through what needs a person after
  `generate`: each AI-drafted line (accept, edit, skip), each `TODO` gap
  (fill, skip), and each comment a new docstring now repeats (remove only
  on an explicit yes; the default keeps it). Only docstring lines and
  approved comments change, and a file is saved only if it still parses
  with exactly the same code. `--list`, or running without a terminal,
  lists the items and changes nothing.
- **`generate` ends with a summary** of what it did: docstrings written,
  updated (author text kept) or already complete; details taken from the
  code; AI-drafted lines; docstrings taken from comments; and gaps left --
  followed by a suggested next step. Totals cover the whole run for a
  directory. Printed to stderr, so it never mixes with code on stdout.
- **A `#` comment block above an undocumented function or class becomes
  its docstring**: the first sentence as the summary, the rest as the
  description. It counts as the author's own text, so AI drafting never
  replaces it. The comment is left in place -- the tool never deletes
  code. Notes (`TODO`), tool directives (`noqa`, `type:`), commented-out
  code and section banners (blocks with a `# -----` line) are not used,
  and neither is a comment separated from the definition by a blank line.
- **`--ai-draft` fills every gap, not just the description.** A
  name-derived summary, parameters with a TODO or type-only description,
  an undescribed return value, and exceptions without a readable condition
  are drafted in one request per function, using the hosted service's new
  `/v2` endpoint. Author text and facts read off the code are never
  replaced. Every drafted line carries the `(AI-drafted, unreviewed)`
  marker and passes a safety check before it's written (no triple quotes,
  backslashes, placeholder or marker text). Drafts are kept on later runs,
  so regenerating costs no further requests.
- **Bring your own key**: `--ai-provider gemini|openai|anthropic|deepseek|
  openai-compatible` calls that provider directly with your key (read from
  `GEMINI_API_KEY`, `OPENAI_API_KEY`, ... or asked for, hidden), through
  its official SDK installed as an optional extra
  (`pip install "pycodecommenter[gemini]"`, `[openai]`, `[anthropic]`, or
  `[ai]` for all; Python 3.10+). Each provider has a default model
  (Anthropic: `claude-opus-5`; Gemini: `gemini-2.5-flash`), printed at the
  start of every run; `--ai-model` chooses any other, and
  `--ai-base-url` points `openai-compatible` at Mistral, Groq, Ollama, etc.
- **Daily limit, then your own key**: the hosted service now allows 25
  drafts per caller per day. The CLI reports how many are left; when they
  run out mid-run, an interactive run asks whether to continue with your
  own key from that same function, and a CI run stops cleanly and says
  how to continue.
- **Consent per destination**: agreeing to send code to the hosted service
  no longer covers a provider you call directly, or vice versa.
  `--yes-send-code-to-ai` replaces `--yes-send-code-to-hosted-ai`, which
  still works as an alias.
- **`generate --output-dir PATH`** (§6): writes a fully-documented copy of
  a directory target's tree to `PATH`, mirroring each file's relative
  path, leaving the originals untouched — closing the exact gap that made
  `document_folder.py` necessary as a hand-rolled external script for the
  audit. Mutually exclusive with `--inplace`; rejected on a single-file
  target the same way `--output` is already rejected on a directory one.
- **Opt-in module-level docstring generation** (§2), for a module that has
  none at all: `PyCodeCommenter(include_module_docstrings=True)`, or
  `generate --include-module-docstrings` on the CLI. Off by default —
  unlike a missing function/class docstring, a missing module docstring
  would touch the output of nearly every input (any file/snippet with no
  module docstring, not just a `main.py`-shaped real project file lacking
  documentation entirely), so this stays behind an explicit flag, the same
  way `--inplace`/`--backup` already do for other consequential behavior.
  When enabled, the summary is derived from
  the file's name (via `from_file`) or a neutral placeholder (via
  `from_string`, which has no filename to go on), plus a real `Classes:`/
  `Functions:` listing of what the module defines when it defines
  anything — mirroring the `Attributes:`/`Methods:` pattern already used
  for classes. A module with an *existing* docstring is never touched:
  unlike function/class docstrings, this never attempts to merge into one,
  since module docstrings are far more free-form prose and reconstructing
  one risks corrupting it for no benefit.
- **`Raises:` entries state the condition when the code states it
  exactly** (new `code_facts.py`): a `raise` directly under a top-level
  `if` becomes ``ValueError: If `discount < 0`.``, one in the `else`
  branch ``If `x in ALLOWED` is false.``, one in a top-level `except`
  ``If `OSError` occurs.``, and an unconditional one in a function with
  no `return` ``Always.``. Nested, `elif`, in-loop, and over-long
  conditions keep the guess marker, since one clause can't state them
  exactly.
- **`bool` and `str` return types read off return expressions**:
  comparisons, `not`, `isinstance`/`hasattr`-style built-ins and
  `and`/`or` over booleans give `bool`; f-strings and `str` methods on a
  string literal (`" ".join(...)`) give `str`. A function with a single
  boolean return expression gets ``True if `expr`, otherwise False.``
  instead of a guess marker.

### Changed
- **`Methods:` is no longer generated for classes.** It isn't a standard
  Google-style section (the validator already reported it as
  non-standard), every public method carries its own docstring, and the
  generated entries were guess markers only. An author's own `Methods:`
  section is kept; entries left over from earlier runs are removed.

### Fixed
- **Consent prompts could be invisible, leaving `generate` waiting.**
  With the patched code going to stdout (`generate app.py > out.py`), the
  consent question went into `out.py` too. Prompts and status messages now
  go to stderr; stdout carries only generated code.
- **Escape sequences in existing docstrings were rewritten, and could
  break the file.** Existing docstrings were read as their *value*, so a
  written `\n` came back as a real line break on every run -- and escaped
  quotes (`\"\"\"`) came back as a real `"""`, ending the docstring early
  and producing a file that no longer parses. Docstrings are now read from
  their source text, escapes kept as written, and a raw string keeps its
  `r` prefix.
- **An author's `__init__` summary was replaced** with "Initialize the
  class."; that text is now only used for an `__init__` with no docstring.
- **Text from an earlier run was treated as author text**, so its TODO
  markers and type-only filler (`float value.`) could never be improved --
  including by `--ai-draft` on a file generated before it existed. The
  generator now recognises its own earlier output and regenerates it.
- **Defaults were stated twice** (`Default is 3. (default: 3)`); the
  `(default: ...)` suffix is now the only mention.
- **`raise NotImplementedError` (no parentheses) got no `Raises:` entry.**
  A bare raise of a built-in exception, or of a name following the
  exception-class convention (`ConfigError`), is now documented; `raise
  err` (an instance) still isn't guessed.
- **Regeneration overwrote author-written `Raises:`, `Attributes:` and
  `Methods:` text.** An author's exception and attribute descriptions
  were replaced with guess markers (or inferred filler) on every run, and
  a hand-written `Methods:` section was deleted, so running the tool on a
  fully documented file made it less documented. `DocstringParser` now
  parses Google, Sphinx (`:raises X:`) and NumPy `Raises` entries, and
  Google `Attributes:`/`Methods:`, and the generator carries them forward.
  Exceptions or attributes the author documented but the code doesn't
  raise/assign directly (propagated exceptions, class constants) are kept.
- **Name inference matched "count"/"num" inside other words**:
  `discount` became "Number of dis." and `country` "Number of try.".
  Matching is now by whole word.
- **Untyped class attributes were shown as `(any)`** while the same
  parameter in `Args:` showed `(Any)`.
- **CRLF files were silently normalized to LF on every generation run**
  (§3), even on files with zero docstring changes — turning a
  documentation PR on a CRLF file (common on projects with Windows
  contributors) into a full-file line-ending diff. `from_file`/
  `from_string` now detect and remember the source's newline convention,
  normalizing to `\n` only for internal processing; `get_patched_code()`
  restores the original convention at the final output boundary. The CLI's
  `--inplace`/`--output`/`--output-dir` reads and writes now use
  `newline=""` too, so the before/after comparison isn't fooled by
  universal-newlines translation and a CRLF file isn't double-translated
  to `\r\r\n` on write on Windows.
- **An unexpected exception mid-generation silently discarded a real,
  existing docstring** (§5), replacing it with the unhelpful literal
  `"""Error generating docstring."""` — a `document_folder.py`-style
  driver script's own `[OK]`/`[FAIL]` reporting would never see this,
  since the failure was per-function, not per-file. `_generate_function_
  docstring`/`_generate_class_docstring` now fall back to the original
  docstring when one existed, matching the fallback discipline this file
  already uses for a libcst parse failure elsewhere. Unobserved in
  practice before this fix (the audit flagged it as a latent risk, not an
  encountered bug), so verified by forcing a real exception directly
  rather than against a naturally-occurring repro.
- **`__init__` was the one function still getting fixed boilerplate
  description text on every constructor**, regardless of what the class
  does (`"Initialize a new instance."`, ten times across this project's
  own source alone) — inconsistent with the "no placeholder paragraph"
  principle already applied to every other function earlier in this
  thread. `__init__`'s description now follows the same rule as
  everywhere else; only the summary line (`"Initialize the class."`)
  stays fixed, since the generic name-derived fallback would produce
  `"Init."` for `__init__`, which reads worse than what it would replace.
- **A `@property`'s getter/setter/deleter were listed three times under
  one name in a class's `Methods:` section** (§1.8), with no indication
  which was which. The `Methods:` list was built from every non-private
  method in the class body with no deduplication — but a setter/deleter's
  decorator (`<property_name>.setter`/`.deleter`) is only valid Python
  when it rebinds the exact same name as the property, so any duplicate
  name here is always one property's accessor trio, never two distinct
  methods. Fixed: the method-name list now dedupes via `dict.fromkeys()`,
  preserving first-seen order.
- **The validator false-flagged its own honest output on `Returns`/
  `Yields`** (§1.6). `check_return_documentation` treated any non-empty
  parsed `Returns:` text as a claim of a real return value, so every void
  function documented with the generator's own honest `Returns:\n
  None.\n` convention was flagged "has Returns section but doesn't return
  a value" — a `generate` → `validate` CI pipeline produced spurious
  warnings on its own freshly generated, correct output. A real generator
  got the identical false positive, because the check only recognized
  `ast.Return`, never `ast.Yield`/`ast.YieldFrom` — a generator's genuine
  yielded value was invisible to it. Fixed: the output-value scan now
  includes `yield <value>`, and the literal `"None."` sentence no longer
  counts as "claims a return value." On the audit's own dogfood fixture,
  this dropped the validator's `returns`-category issue count from 5 to 0
  with no new categories introduced.
- **NumPy `Raises` sections corrupted the merged docstring, and did so
  worse after `Raises:` generation was added** (§1.3). An unrecognized
  NumPy `Raises` section used to be folded into the free-text
  `description`, producing malformed output (no longer valid Google or
  NumPy style — it lost its `------` underline without gaining a `:`, and
  floated above `Args:`/`Returns:`). Once real `Raises:` generation
  existed (see Tier 2a below), regenerating a file with this shape
  produced *two* disagreeing Raises blocks: the stale, malformed leftover,
  and a correct, freshly-generated one naming the same exception.
  `docstring_parser.py`'s NumPy `Raises` handling now discards the body
  entirely, matching the design already used for the Google-style
  `Raises:` header: the exception class is always recomputed fresh from
  the function's actual `raise` statement, so there's nothing to merge
  back in.
- **String forward-reference type annotations (`-> "ClassName"`) resolved
  to `Any` instead of the named type** (§1.4). `type_analyzer.py`'s
  `get_annotation_type` handled `ast.Constant` only for the `None`
  annotation; any other constant -- i.e. any quoted forward reference, PEP
  484's way of naming a type not yet defined at the annotation's point in
  the source -- fell through to `"any"`. This hit the tool's own public
  API: `PyCodeCommenter.from_string`/`from_file` both declare `->
  "PyCodeCommenter"` (the standard fluent-builder self-return pattern) and
  got `Returns: Any: ...` instead of `Returns: PyCodeCommenter: ...`. Also
  affects any self-referencing factory/builder method (confirmed on
  `OrderProcessor.empty(cls, ...) -> "OrderProcessor"` and
  `Coordinates.distance_to(self, other: "Coordinates")` in the audit's own
  fixture) and resolves correctly nested inside a generic too (e.g.
  `Optional["ClassName"]`), since the fix is in the same recursive
  `get_annotation_type` call every subscript/union branch already goes
  through.
- **`generate` was not idempotent: regenerating on already-patched output
  compounded without bound.** Every rerun on a file with a defaulted
  parameter appended another copy of `" (default: ...)"` onto that
  parameter's Args: line (`rate (float): float value. (default: 0.1)` →
  `... (default: 0.1). (default: 0.1)` → `... (default: 0.1). (default:
  0.1). (default: 0.1)`, unbounded), and a niladic function's `Returns:
  None.` became `Returns: None: None.` on the very next regeneration.
  Root cause: `DocstringParser` re-parses the tool's own previously
  generated Args-line suffix and bare `"None."` return sentence back as if
  they were free-form author text, and `commenter.py` re-wrapped them
  instead of recognizing its own prior output — the same defect shape as
  the `Raises:`/NumPy-`Returns:` merge bugs above, for two more
  tool-generated literals. Pre-existing; reproduces identically on the
  untouched pre-Tier-2a checkout. Fixed: a new
  `_strip_own_default_annotation` (`commenter.py`) strips *any* trailing
  `" (default: ...)"` suffix from a re-parsed parameter description before
  deciding what to append — unconditionally, not only when it happens to
  match the parameter's current default, since the append immediately
  below always re-adds the correct, current one regardless. (An earlier
  version of this fix matched only the current value, which left a gap:
  editing a parameter's default in source between `generate` runs — a
  normal workflow — left the stale suffix in place alongside a freshly
  appended current one, the same compounding failure via a legitimate edit
  instead of a bare rerun.) The bare `"None."` return sentence is now
  recognized and treated as absent (not real preserved text) before the
  existing-description merge branch runs — falling through correctly to a
  fresh guess marker if the function has since been edited to actually
  return a value, rather than keeping the stale text forever. Verified
  stable across 4 consecutive regeneration passes — including across a
  changed default value — and on the full
  `docstring_generation_fixture.py`.
- **Generation injected an unwanted `TODO(pycodecommenter): describe`
  paragraph into docstrings that were already complete.** `commenter.py`'s
  `_generate_function_docstring`/`_generate_class_docstring` treated "no
  free-text description paragraph was parsed" as "a description is
  missing," even when a docstring's summary + `Args:` + `Returns:` was
  already complete by design (a normal, common Google-style shape with no
  separate prose paragraph). Merging into `slugify`'s own already-correct
  docstring — used as the maintainer's own "leave this alone" regression
  fixture — reproducibly injected the placeholder instead of leaving the
  docstring untouched. Fixed: the description slot is now only ever filled
  with real parsed text; it's left empty otherwise, whether or not a prior
  docstring existed. (A fresh, never-documented function's summary line is
  itself just derived from the function's name, so a second "nothing to
  add" paragraph immediately below it added no information beyond what the
  summary already didn't have — this now no longer appears either. Per-field
  placeholders — `Args:`/`Returns:`/`Attributes:`/`Methods:` entries with no
  other source of truth — are unaffected.)
- **A hand-wrapped summary sentence spanning multiple physical lines got
  split at the wrap point.** `DocstringParser.parse()` took only the docstring's
  first physical line as "the summary," so any existing docstring whose
  summary sentence wrapped across two or more lines (common style throughout
  this project's own source, e.g. `param_utils.py`'s `_walk_until`) had its
  second line treated as a separate description paragraph — severing the
  sentence mid-thought. Fixed: the summary is now the whole first paragraph
  (every physical line up to the first blank line or a recognized section
  header), joined back into one line.

### Added
- **Class `Attributes:` descriptions now go through the same
  `infer_description()` pipeline `Args:` already uses**, instead of an
  unconditional `TODO(pycodecommenter): describe` for every attribute.
  `OrderProcessor.customer_id` now reads "Unique identifier for the
  customer." instead of a guess marker; an attribute with no matching
  name/type signal (e.g. `ConfigError.original`, typed
  `Optional[Exception]`) still correctly gets the guess marker.
- **Functions that `raise` now get a `Raises:` section naming the exception
  class.** Previously the generator only ever wrote `Args:`/`Returns:`/
  `Yields:` — even for a function whose body raised, which meant running
  `validate` against the tool's own generated output flagged its own
  docstrings ("Function raises exceptions {'ValueError'} but has no Raises
  section"). The exception *class* at a `raise SomeError(...)` site is a
  literal token in the source (a fact); only *why*/*when* it's raised is
  unknowable from the AST, so that part is still an explicit
  `TODO(pycodecommenter): describe when this is raised.` marker. A bare
  `raise` (re-raise) and `raise err` (an already-constructed instance) are
  correctly skipped rather than guessed, since neither lets the exception
  class be read off the raise site without data-flow analysis.
  `docstring_parser.py` also now recognizes `Raises:` as a real Google-style
  section header (it previously didn't), so re-running `generate` on
  already-Raises-documented output doesn't glue the Raises block onto the
  `Returns:` text above it — the same corruption shape as the pre-existing
  NumPy-`Raises` bug, now pre-empted for this new section too.
- **`inference.py`'s name-pattern vocabulary widened**: `id`/`*_id`,
  `name`/`*_name`, `key`/`*_key`, `index`/`idx`, `config`/`configuration`/
  `settings`/`options`, `result`/`output` now produce a real, specific
  description (e.g. `customer_id` → "Unique identifier for the customer.")
  instead of falling through to the generic type-only fallback or the
  guess marker. Existing, more specific rules (`*_path`, `is_`/`has_`/
  `can_`, `count`/`num`) keep priority — the new rules are checked last and
  never shadow them.

## [2.5.0] - 2026-09-05

### Added
- `--version` flag on the CLI, printing the installed version and exiting 0.

### Fixed
- **`validate`'s exception/return checks misattributed a nested function's
  `raise`/`return` to the outer function.** `check_return_documentation` and
  `check_exception_documentation` used a raw `ast.walk(func_node)`, which
  descends into nested `def` bodies — a closure or helper function's own
  `raise`/`return` produced a false-positive WARNING on the *enclosing*
  function. `commenter.py` already had the fix for the identical bug class
  (`_walk_function_body`, used by `_is_generator`/`_get_return_type`) but it
  was never shared with `validator.py`. Both now share
  `param_utils.walk_own_scope`.
- **`_get_class_attributes` had the same class of bug, twice.** A `self.x =
  ...` assignment inside a *class* nested within `__init__` was
  misattributed to the outer class's `Attributes:` section (fixed with a
  new `param_utils.walk_skipping_nested_classes`, which — unlike
  `walk_own_scope` — still descends into nested *functions*/closures, since
  those legitimately share the enclosing `__init__`'s own `self`). Separately,
  `__init__`'s own parameters were read directly from `func_node.args.args`
  instead of the shared `get_all_parameters()`/`exclude_self_cls()`
  primitive, so keyword-only params and `**kwargs` got `(any)` in the
  `Attributes:` section instead of their real type — inconsistent with the
  correct type already shown for the same parameter in the `Args:` section
  a few lines below.
- Negative-number default values (e.g. `x=-1`) rendered as
  `(default: unknown)`. `ast` represents a signed numeric literal as
  `UnaryOp(USub, Constant(...))`, not a single `Constant` — `_get_default_value`
  only handled the latter.
- `pycodecommenter coverage <file>` crashed with a raw traceback (instead of
  a clean error and exit 1) when the target file couldn't be parsed or
  didn't exist. `CoverageAnalyzer.analyze_file()` had no error handling
  around its own `open()`/`ast.parse()`, unlike `analyze_directory()`'s
  per-file wrapping; `generate`/`validate` already handled this case
  gracefully for a single file.

### Removed
- `parameter_descriptions.py`, a hardcoded dictionary of parameter
  descriptions keyed to ~17 exact function names (`calculate_area`,
  `send_email`, `connect_to_database`, etc.), consulted ahead of the
  general rule-based inference in `inference.py`. It never generalized
  beyond those exact names and fell through safely regardless — removed in
  favor of `inference.py` alone. A function whose name and parameter
  exactly matched one of those entries will now get
  `TODO(pycodecommenter): describe` for that parameter instead of the old
  canned sentence, same as any other parameter `inference.py` has no
  signal for.

## [2.4.0] - 2026-08-24

### Added
- New shared `PyCodeCommenter/param_utils.py` primitive
  (`get_all_parameters`/`exclude_self_cls`), fixing five independent blind
  spots where positional-only params, keyword-only params, `*args`/`**kwargs`,
  and dataclass/self-assigned class attributes were silently invisible to
  both docstring generation and validation — all three sites that inspected
  a function's parameters (the generator's Args-writer, and two validator
  checks) previously rebuilt that list from `func_node.args.args` alone.
- Generator functions (containing a `yield`) now get a `Yields:` section
  instead of an incorrect `Returns: None`.
- `--badge-output PATH` flag on `pycodecommenter coverage` (and the
  underlying `coverage.shields_badge_dict()`), emitting a shields.io
  endpoint-badge JSON file for the coverage percentage.
- CI now runs the full test suite, including `inference.py`'s doctest
  examples, on every push/PR against `main`
  (`.github/workflows/tests.yml`, new; matrix over Python 3.9-3.12).

### Changed
- README repositioned to be explicit that generated prose the tool can't
  extract from the AST is a marked placeholder needing review, not finished
  documentation, and to name related tools (pydoclint, interrogate) instead
  of implying PyCodeCommenter is alone in this space. The Roadmap's
  AI-generation item was replaced with a struck-through line plus a warning
  block spelling out the draft-and-review-only constraint, so it can't be
  misread as an open, unclaimed feature.

### Fixed
- Guessed (as opposed to AST-extracted or preserved) docstring content is now
  marked with `GUESS_MARKER = "TODO(pycodecommenter): describe"` instead of
  being presented as finished prose. This string is already in
  `validator.py`'s placeholder blacklist, so generated output with
  unresolved guesses now fails the tool's own quality check instead of
  silently passing it.
- `_get_class_attributes` now also picks up `self.x = ...` assignments
  anywhere in `__init__`'s body (not just `__init__`'s own parameters) and
  class-level `AnnAssign` fields (covers `@dataclass`-style classes with no
  `__init__` written in source).
- `@classmethod`-decorated functions no longer document `cls` in the
  generated Args section (the generator only excluded `self`; the validator
  already excluded both).
- **Python 3.9 import crash in `config.py`.** A live (non-deferred)
  `Exception | None` default-argument annotation needs Python >=3.10 —
  `type.__or__` for builtin/exception types doesn't exist on 3.9, so
  evaluating it at class-definition time (import time) raised `TypeError:
  unsupported operand type(s) for |: 'type' and 'NoneType'`. Since `cli.py`
  imports `config.py`, this broke collection for the entire test suite on
  3.9. Pre-existing since v2.1.0 (2026-06-10), roughly three months before
  this release — caught by this release's own new CI matrix (see above) on
  its first real run. Fixed with `Optional[Exception]` plus `from
  __future__ import annotations`, matching the guard `inference.py` already
  uses for its own `str | None` usage.

## [2.3.0] - 2026-08-22

Follow-up work from an internal engineering audit (`Future Work/Vulnerabilties.md`),
plus a documentation-fidelity pass (Phase 6) found during pre-release review.

### Breaking Changes
- **Minimum Python version raised from 3.8 to 3.9.** `pyproject.toml`'s
  `requires-python` is now `>=3.9`; the `Programming Language :: Python :: 3.8`
  classifier was removed. This was forced by the new `libcst` dependency (see
  below), whose current release requires Python >=3.9. **Any user still on
  Python 3.8 will no longer be able to install new releases of this package.**

### Added
- **New runtime dependency: `libcst>=1.1`.** `get_patched_code()` (the code
  that inserts/updates generated docstrings) was rewritten to apply edits via
  libcst's concrete syntax tree instead of line-number arithmetic on raw
  source text. This is a hard dependency, not optional — installing
  `pycodecommenter` now also installs `libcst`.
- `generate` and `validate` CLI commands now accept a directory as well as a
  single file, recursively collecting `.py` files (mirroring `coverage`'s
  existing directory support).
- `--fail-below THRESHOLD` flag on the `coverage` CLI command; exits 1 when
  coverage is below the threshold.
- `.pycodecommenter.yaml` config is now actually read by the CLI: its
  top-level `exclude` list defaults `-e/--exclude` on all three subcommands,
  and `coverage.threshold` defaults `--fail-below`. Both remain overridable
  by explicit CLI flags. (Previously `config.py` existed but nothing called it.)
- NumPy-style docstrings (`Parameters`/`Returns`/`Raises` with dash-underlined
  headers) are now parsed as input, alongside Google and Sphinx style.
  Sphinx-style input also gained `:type name: TYPE` support.

### Fixed
- **One-line function/class definitions could corrupt the file when patched.**
  `def foo(): return 1` (body on the same physical line as the `def`) would
  have its generated docstring inserted *before* the `def` line instead of
  inside the function, producing a `SyntaxError`. Every one-liner shape
  reproduced this: `pass`, `return`, multiple `;`-separated statements,
  `async def`, and one-line `class` bodies. Fixed by the libcst rewrite above,
  which converts a one-liner body to a proper indented block before inserting.
  (This is a different, narrower bug than the "multi-line signature
  corruption" originally suspected from the audit — see Notes below.)
- `PyCodeCommenter.validate()` now passes the real file path to the validator
  instead of a hardcoded `None`, so validation report locations show the
  actual file (e.g. `src/api.py:12:my_func`) instead of `code:12:my_func`.
- `PyCodeCommenter.check_coverage()` now uses the real file path instead of
  the leaked `"<string>"` placeholder.
- `docstring_parser.py`: multi-line `Args:` parameter descriptions in an
  *existing* docstring being re-parsed were silently truncated unless the
  continuation line was indented by exactly 8 spaces. Any other indentation
  (including 4 spaces — the same indent this project's own generator uses)
  lost the continuation text on merge. Now any non-blank continuation line is
  recognized regardless of indentation depth.
- `generate`/`validate` directory mode's default exclude list
  (`__pycache__`, `.git`, `.venv`, `venv`, `env`, `.eggs`) missed common
  vendor/build directories and used raw substring matching, causing two real
  problems: `environment_config.py` was silently skipped (`"env"` is a
  substring of `"environment"`), and files inside `.tox/.../site-packages/`
  were *not* skipped — with `generate --inplace`, writing generated
  docstrings into vendored third-party source. Expanded the default list
  (added `.tox`, `.nox`, `__pypackages__`, `site-packages`, `build`, `dist`,
  `.egg-info`, `.mypy_cache`, `.pytest_cache`, `node_modules`) and switched
  to exact-path-component matching. `coverage`'s directory mode had the same
  two problems independently (a separate, duplicated exclude list) and is
  fixed the same way, plus a related bug: passing any custom `--exclude`
  pattern previously replaced its default list entirely rather than adding
  to it, silently losing `.venv`/`.git` protection.
- A parameter's documented type (e.g. `x (int):`) was silently downgraded to
  `x (any):` on regeneration whenever static type inference had nothing to
  work with (no annotation on the parameter) — the type was parsed out of
  the existing docstring but never stored or consulted. A real static
  annotation still always wins; the docstring-parsed type is now used as a
  fallback instead of being discarded.
- An existing NumPy-style docstring was not recognized as such, so its
  entire body was treated as free-text and a fresh, auto-generated
  Google-style `Args:`/`Returns:` section was appended underneath it —
  documenting the same parameter twice, in two styles, in one docstring.
- Generated filler text for dunder methods (e.g. `__init__`) rendered with
  broken spacing — `"Original of the   init  ."` — because
  `name.replace('_', ' ')` turns every underscore into a space, including
  the leading/trailing pair(s) dunder names have.

### Changed
- `ValidationStats.infos` renamed to `.info` (matches the existing `"info"`
  key in JSON/markdown output). `.infos` remains available as a
  backward-compatible property alias.

### Notes
- Two "CRITICAL" bugs originally suspected from the audit — corruption on
  multi-line function signatures, and a line-shift bug when patching multiple
  functions in one file — were investigated and do not reproduce against this
  version or the pre-libcst version; both were verified directly against the
  audit's own examples plus additional stress tests. No code changes were
  made for either.
- A third suspected bug — `ast.walk()` double-counting nested
  functions/classes in `validate_all()`'s stats — also does not reproduce;
  `ast.walk()` visits every node exactly once regardless of nesting depth.
  `validator.py`'s counting logic is unchanged.
- PEP 604 union rendering (`int | str` currently renders as `Union[int, str]`
  in generated docstrings, per `type_analyzer.py`) was identified as a real,
  minor issue but deliberately deferred: fixing it breaks
  `test_type_analyzer.py::test_union_annotation`, which asserts the old
  `Union[...]` output, and no test-file changes were in scope for that part
  of the work.

## [2.2.0] - 2026-07-12

### Added
- **Decorator-aware validation** — `@property` setter and deleter variants no longer produce false-positive
  "missing Returns section" warnings. `@classmethod` (`cls`) and `@staticmethod` were verified already correct.
- **`--output-format json`** flag on both `validate` and `coverage` subcommands. Prints machine-readable
  JSON to stdout; text output is completely unchanged.
- **`ValidationReport.to_dict()`** updated to spec-compliant shape: `stats.total`, `stats.info`,
  `stats.coverage_percentage`; issues now include `line` (integer), `severity` (uppercase), `check`, `message`.
- **`_has_raises_section()` helper** in `validator.py` — recognises `Raises:` (Google), `Raises\n`
  (bare header), and `:raises ` (Sphinx, trailing space prevents false matches).
- **`llms.txt`** file at repo root — AI agent and LLM crawler discovery file.
- **SEO/AEO optimisation** — keyword-rich README, PyPI classifiers/keywords, per-page meta tags on all
  doc pages, JSON-LD `SoftwareApplication` schema on docs homepage.

### Changed
- `test_validation.py` rewritten from script-style to proper pytest (17 tests, all pass).
- `pyproject.toml` keywords expanded to 20 terms; classifiers expanded with `Code Generators`,
  `Libraries :: Python Modules`, `Environment :: Console`, `Operating System :: OS Independent`.
- `mkdocs.yml` enriched with `site_author`, explicit `language: en`, `navigation.indexes`,
  `search.share`, `toc.follow`, and `meta` markdown extension for per-page SEO tags.

## [2.0.0] - 2026-01-25

###  Major Release - Complete Rewrite

#### Added
- **Comprehensive Validation System** - 6 types of documentation checks
- **Coverage Analysis** - Project-wide documentation metrics
- **Modern Type Support** - PEP 604 unions, PEP 585 generics
- **Async Function Support** - Full support for `async def`
- **Multiple Export Formats** - JSON, Markdown, console output
- **Smart Docstring Parsing** - Preserves existing documentation
- **Structured AST Traversal** - NodeVisitor pattern for reliability
- **Professional Reporting** - Actionable error messages with suggestions
- **CI/CD Ready** - Easy integration with pipelines

#### Changed
- Replaced basic type inference with comprehensive `TypeAnalyzer`
- Improved docstring generation with better templates
- Enhanced error handling with proper logging
- Better handling of edge cases and malformed code

#### Fixed
- Duplicate `_infer_type` methods consolidated
- Brittle patching logic made robust
- Import resolution issues
- Unicode/encoding handling

#### Breaking Changes
- Minimum Python version: 3.8+
- Some internal APIs changed (public API remains compatible)

## [1.0.0] - Earlier Version

- Basic docstring generation
- Template-based descriptions
- File and string input support
