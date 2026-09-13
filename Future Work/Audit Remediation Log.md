# Audit Remediation Log

Running record of fixes made in response to the three audit/report threads
against `Another_Test_PyCodeCommenter`:

- `Feedback/AUDIT_REPORT.md` — the original 31-file generation audit.
- `AGENT_PROMPT_TODO_REDUCTION.md` — the Tier 2a/2b TODO-reduction task.
- `Feedback/IDEMPOTENCY_BUG.md` — the regeneration-compounding bug found
  while verifying Tier 2a.

Each entry: what was found, what changed (file:line), how it was verified,
and current status. Newest work at the top. This file is a work log, not a
spec — see the source documents above for the original findings in full,
and `CHANGELOG.md` for the release-facing summary of the same changes.

---

## Closed

### Tier 2b, live implementation — GeminiDescriptionProvider

The maintainer decided: Gemini, multiple free-tier API keys with automatic
failover. Reference architecture: a multi-provider chat orchestrator
(`/home/amos/dev/react/Portfolio/portfolio/src/lib/ai-orchestrator`) —
per-key circuit breaker, sequential fallback chain, retry-with-backoff
within one key before moving to the next. Only the failover *shape* was
reused; the reference's chat/streaming/tool-loop/telemetry machinery is
irrelevant to a one-shot "describe this function" call.

- **New `PyCodeCommenter/gemini_provider.py`**: `GeminiDescriptionProvider`
  (real `DescriptionProvider` implementation). Per-key circuit breaker
  (closed → open on 2 consecutive failures or immediately on HTTP 429 →
  60s cooldown → half-open probe); one non-429 failure gets one retry
  before moving to the next key; every key exhausted → `None` (fails
  closed, never fabricates). `from_env()` loads `.env` via `python-dotenv`
  (new dependency, `[ai]` extra only, imported lazily) searching from the
  process's CWD — deliberately, not dotenv's own default (see below).
  `--max-ai-calls` cap checked before every individual attempt, shared
  across a whole provider instance.
- **Real bugs caught before/during the first live call, each verified
  against the real API rather than assumed:**
  1. **Wrong default model.** `gemini-2.0-flash` (my training-data-era
     default) no longer exists on this account's endpoint — confirmed via
     one live, read-only `ListModels` call (explicitly asked for and
     approved before making it). Initially "fixed" by switching to the
     hardcoded literal `gemini-flash-latest` — the user correctly pushed
     back on this as the same mistake in a different spot (pointing at the
     reference orchestrator's own `discoverBestModel`/`GeminiModelSelector.
     ts`, which queries `models.list` live instead of trusting a fixed
     name). Superseded below.
  2. **`load_dotenv(dotenv_path, usecwd=True)` doesn't exist** — `usecwd`
     is a `find_dotenv` parameter, not `load_dotenv`'s. Caught by the
     automated test suite (3 failures), not by a live call. Fixed to
     `find_dotenv(usecwd=True)` then `load_dotenv(that_path)`.
  3. **`python-dotenv`'s default search is relative to the *importing
     module's* file location, not the process's CWD** — an intended "no
     keys configured" test from `/tmp` accidentally found and loaded the
     real project `.env` anyway, making 8 unintended live calls (all
     failing on bug #1's stale model name — no generation actually
     happened, but real quota was still spent on wasted attempts).
     Confirmed via `find_dotenv()` directly rather than guessing why.
     Stopped, disclosed the accidental spend, and got an explicit decision
     (search from CWD instead) before continuing.
  4. **Silent truncation on "thinking" models.** The first live
     `generateContent` call after fixing bugs 1–3 returned a docstring
     paragraph truncated mid-sentence. Diagnosed by inspecting the raw API
     response directly rather than guessing: `gemini-flash-latest`
     currently resolves to `gemini-3.8-flash`, a "thinking" model that was
     spending its entire `maxOutputTokens` budget (200) on invisible
     internal reasoning (`thoughtsTokenCount: 241`) before writing any
     visible answer, some of the time returning `finishReason: MAX_TOKENS`
     with empty content. Fixed with `generationConfig.thinkingConfig.
     thinkingBudget: 0` — confirmed via a live call showing a full, correct
     sentence, `finishReason: STOP`, and real token usage dropping ~4x
     (277 → 63 tokens), which also directly helps the daily-quota concern
     `--max-ai-calls` exists to guard.
- **CLI wiring** (`cli.py`): `generate --ai-draft` (constructs the shared
  provider once per invocation, reused across every file in a directory
  run — not rebuilt per file, or circuit-breaker/call-count state would
  reset every file), `--accept-ai-drafts` (required alongside `--ai-draft`
  only when combined with `--inplace`; `--dry-run`/`--output-dir` need
  `--ai-draft` alone, since both already exist as review-first paths —
  confirmed `--output-dir` was actually already built, not assumed, after
  a direct question about whether the plan was quietly depending on
  unbuilt work), `--max-ai-calls N` (default 20 when `--ai-draft` is used
  without it; `0` for unlimited).
- **The dedicated pipeline test, explicitly required rather than left
  implied**: `test_gemini_provider_marked_and_categorized_through_full_
  pipeline` (`test_gemini_provider.py`) runs the *real* `GeminiDescription
  Provider` (network mocked at `_post` only) through `PyCodeCommenter →
  get_patched_code() → DocstringValidator.validate_all()`, asserting the
  `(AI-drafted, unreviewed)` marker is present, the `ai_draft` category
  fires exactly once at `Severity.WARNING`, and nothing else does —
  proving the Tier 2b marker/validator scaffolding survives contact with
  the real provider, not just a hand-written stub.
- **Model discovery, added after the hardcoded-literal fix above was
  correctly rejected.** `_resolve_model`/`_discover_model`/`_list_models`
  (`gemini_provider.py`): `model=None` (the new default; an explicit
  `model=` string still skips discovery entirely) queries `GET /models`
  per key, filtered to `generateContent`-capable models, preferring a
  Google-maintained `-latest` alias first (the one part of this namespace
  built specifically not to go stale — directly informed by having just
  watched `gemini-2.0-flash` and the reference's own hardcoded
  `RANKED_FLASH_MODELS` fallback list both go stale in the same session),
  then any non-preview/experimental "flash" model, then any flash model at
  all, then the constant as the absolute last resort (network/parse
  failure only). Cached per key for 5 minutes so a whole `generate` run
  doesn't repeat the listing call per function. Confirmed live:
  `_model_cache` correctly resolved `gemini-flash-latest` for a real key.
- **Incident: a real API key was briefly exposed in this session's own
  output.** A live diagnostic call printed `provider._model_cache` (keyed
  by raw API key) directly, putting one key's full value into the
  transcript. Caught immediately, disclosed to the user without
  downplaying it, and treated as compromised per this project's own
  standing security rule (a leaked secret gets rotated, not just cleaned
  up) — the user rotated the key before any further live verification
  resumed. No key material appears in this log, in commits, or in test
  fixtures; the fix going forward is to only ever surface derived,
  non-secret diagnostics (key count, resolved model name, success/failure)
  when inspecting this provider's internal state, never the state itself.
- **Verified:** 26 tests in `test_gemini_provider.py` (failover, retry,
  circuit-breaker persistence across calls within one instance, `max_calls`,
  prompt grounding, `from_env` parsing, 10 of them specifically on model
  discovery: alias preference, non-preview fallback, any-flash fallback,
  discovery-failure fallback, nothing-usable fallback, per-key caching,
  explicit-model bypass, and the resolved model actually landing in the
  request URL) + 7 in `test_cli.py` (flag gating, shared-instance-not-per-
  file, `max_calls` plumbing), all against mocks — zero live calls in the
  automated suite. Separately, two full real end-to-end runs (before and
  after the key rotation) each produced a correct, marked, grounded
  sentence with `gemini-flash-latest` resolved live. Full suite 161/161,
  Black/flake8 clean, fixture still 3-pass idempotent and unaffected
  (default `description_provider=None` path untouched).

### §3, §5, §6, and the `"Initialize the class."` boilerplate — batched together

Done together at the user's request to move fast; each is independent.

- **§3 — CRLF silently normalized to LF.** `from_file`/`from_string` now
  detect `\r\n` (`from_file` reads with `newline=""` so Python's universal-
  newlines mode doesn't erase the evidence first) and normalize to `\n`
  internally; `get_patched_code()` restores the original convention at the
  very end, the only boundary that needs to know about it. `cli.py`'s
  `--inplace`/`--output`/`--output-dir` reads and writes all switched to
  `newline=""` too, so the before/after comparison isn't fooled by
  universal-newlines translation and Windows doesn't double-translate an
  already-CRLF string on write. 2 new tests in `test_edge_cases.py`.
- **§5 — silent per-function exception swallowing.** `_generate_function_
  docstring`/`_generate_class_docstring`'s `except Exception` now falls
  back to the original, existing docstring (re-wrapped) when one existed,
  instead of unconditionally replacing it with the destructive
  `"""Error generating docstring."""` placeholder — matching the fallback
  discipline this file already uses for a libcst parse failure. When there
  was truly nothing to fall back to, behavior is unchanged. Verified by
  forcing a real exception via `unittest.mock.patch` (this was previously
  unobserved/latent, per the audit, so there was no naturally-occurring
  repro to test against). 3 new tests.
- **§6 — no `generate --output-dir` for directory targets.** New
  `--output-dir PATH` flag, reusing the existing `_collect_py_files`
  traversal; mirrors each file's relative path under `PATH`, creating
  parent directories as needed, leaving originals untouched, `[OK]`/
  `[FAIL]` per file plus a `Wrote N/M file(s)` summary — closing the exact
  gap that made `document_folder.py` necessary as a hand-rolled external
  script for this audit. Mutually exclusive with `--inplace`; also
  rejected on a single-file target (symmetric to how `--output` is
  rejected on a directory target). 3 new tests in `test_cli.py`.
- **The `"Initialize the class."`/`"Initialize a new instance."`
  boilerplate.** The description slot for `__init__` was the one function
  still getting fixed boilerplate text on every single constructor,
  regardless of what the class does — inconsistent with the "no
  placeholder paragraph" principle already established for every other
  function earlier in this thread. `__init__`'s description now follows
  the exact same rule as everywhere else (parsed text, or an opt-in
  provider draft, or empty) — only the summary line (`"Initialize the
  class."`) stays a fixed literal, since `humanize_identifier("__init__")`
  → `"Init."` reads worse than the boilerplate it would replace. 1 new
  test.

Verified together: full suite 132/132, Black/flake8 clean, fixture still
3-pass idempotent and unchanged at 22 issues/1 category.

### §2 — no module-level docstring generation

- **Finding:** `DocstringVisitor` implemented `visit_FunctionDef`/
  `visit_AsyncFunctionDef`/`visit_ClassDef` but no `visit_Module` —
  `main.py`-shaped files (no docstrings anywhere, module or otherwise) got
  none added.
- **Design detour, found during implementation, not before:** an
  always-on `visit_Module` fix broke 4 existing tests immediately, because
  it changes the output of *nearly every* input, not just `main.py`-shaped
  real project files — any test snippet with no module docstring (which is
  most of them) would now get one too. This is a much bigger default-
  behavior change than any other fix in this whole thread. Stopped and
  asked before proceeding rather than updating every affected test to
  accommodate a new default; the maintainer chose an opt-in flag,
  consistent with this tool's existing pattern of gating consequential
  behavior (`--inplace`, `--backup`, Tier 2b's provider) behind explicit
  opt-in rather than a silent default change.
- **Fix:** `PyCodeCommenter(include_module_docstrings=True)` (default
  `False`, so all existing behavior — and every existing test — is
  unaffected); wired through to a new `generate --include-module-
  docstrings` CLI flag (`cli.py`, both the single-file and directory-target
  code paths) so the actual reported problem (real files via `generate`)
  is genuinely fixable, not just possible in library code. `commenter.py`:
  `DocstringVisitor.visit_Module` (gated on the flag, and on the module
  having no existing docstring and a non-empty body), `_generate_module_
  docstring`/`_default_module_summary` (summary from the file's stem when
  `from_file` gives one, else a neutral "Module docstring." placeholder;
  real `Classes:`/`Functions:` listing when the module defines any,
  mirroring the `Attributes:`/`Methods:` pattern already used for classes),
  and `_DocstringCSTPatcher.leave_Module` (module-level insertion needed a
  separate mechanism from the position-keyed `edits` dict used for
  functions/classes, since `ast.Module` has no `.lineno`/`.col_offset` at
  all).
- **Deliberate scope boundary:** a module with an *existing* docstring is
  never touched at all — no merge attempt, unlike functions/classes.
  Module docstrings are much more free-form, hand-written prose; parsing
  and reconstructing one risks corrupting it for no benefit, when the
  actual gap is files with none at all. Verified this project's own
  richly-documented modules round-trip untouched with the flag on.
- **Verified:** `main.py`'s exact shape now gets `"""Main."""` with the
  flag on, nothing with it off (both via the library and the real CLI
  `--dry-run`); a leading module comment stays above the inserted
  docstring, not swallowed; a genuinely empty module still gets nothing
  even with the flag on (matches the pre-existing, already-tested empty-
  file behavior); idempotent across 4 passes with the flag on, including
  the full fixture (which already has its own module docstring and
  correctly stays untouched). 8 new tests in `test_edge_cases.py`. Full
  suite 123/123, Black/flake8 clean, fixture unaffected by default
  (22 issues/1 category, unchanged).

### §1.8 — `@property` getter/setter/deleter listed three times in `Methods:`

- **Finding:** `commenter.py`'s class-`Methods:` list is built from every
  non-private `FunctionDef`/`AsyncFunctionDef` in the class body with no
  deduplication, so a property's getter, `@x.setter`, and `@x.deleter` —
  three separate AST nodes sharing one name — all got listed, showing
  e.g. `value()` three times with no indication which was which.
- **Fix:** `commenter.py:410-421` — dedupe the method-name list via
  `dict.fromkeys()` (preserves first-seen order). Safe unconditionally,
  not just for properties: valid Python requires a setter/deleter's
  decorator to literally be `<property_name>.setter`/`.deleter`, rebinding
  the same name, so any duplicate name in a class body is always the same
  property's accessor trio, never two independently meaningful methods.
- **Verified:** the exact `Box` repro from the audit's evidence appendix
  now lists `value()` once; a mixed case (real property trio alongside two
  genuinely distinct methods) confirmed the fix doesn't over-collapse —
  `render()`/`close()` both still listed, `size()` (the property) listed
  once, correct order preserved throughout. 2 new tests in
  `test_edge_cases.py`. Full suite 116/116, Black/flake8 clean, fixture
  still 3-pass idempotent (unaffected — no property trios in it).

### §1.6 — generator/validator false positives on Returns/Yields

- **Finding, two instances:** (1) `validator.py`'s
  `check_return_documentation` flagged "Function has Returns section but
  doesn't return a value" on every void function documented with the
  generator's own honest `Returns:\n    None.\n` convention — the check
  treated any non-empty `parser.returns` as a claim of a real return
  value, without recognizing the tool's own "no value" sentence. (2) A real
  generator (`iter_batches`, with a genuine `yield <value>`) got the same
  false positive, because the check only looked for `ast.Return`, never
  `ast.Yield`/`ast.YieldFrom` — so a generator's real yielded value was
  invisible to it, and its correctly-generated `Yields:` section (which
  shares the same `returns` parser field as `Returns:`) looked like an
  unfounded claim.
- **Fix:** `validator.py`'s `check_return_documentation` — broadened the
  output-value scan to include `yield <value>` alongside `return <value>`
  (`has_output_value`), and added a `documents_output_value` check that
  excludes the literal `"None."` sentence from counting as "the docstring
  claims a return value." Left the opposite-direction branch (real value,
  no Returns section at all) on raw `parser.returns` truthiness,
  unchanged, since it wasn't part of the reported false positives.
- **Verified:** both reported false positives eliminated on their exact
  shapes; confirmed the true-positive direction still fires (real
  return/no section, real yield/no section) — the yield case is a
  previously-existing false *negative* also fixed as a direct consequence
  of the same broadened scan, not a separate change. 3 new tests in
  `test_validation.py`. On the real dogfood fixture: the `returns`
  category dropped from 5 issues to 0, with no new categories introduced
  (22 `quality` issues, unchanged). Full suite 114/114, Black/flake8
  clean, fixture still 3-pass idempotent.

### §1.3 — NumPy `Raises` section merge corruption

- **Finding:** an unrecognized NumPy `Raises` section was folded into
  `description`, producing malformed output (floats above `Args:`/
  `Returns:`, loses its `------` underline without gaining a `:`, not
  valid Google or NumPy style). Confirmed on `config.py`'s real
  `load_config`. **More severe after Tier 2a:** since real `Raises:`
  generation now exists (from actual `raise` statements), regenerating
  produced *two* disagreeing Raises blocks — the old malformed leftover
  floating above `Args:`/`Returns:`, and a correct, freshly-generated
  `Raises:` section at the bottom naming the same exception.
- **Fix:** `docstring_parser.py`'s `_parse_numpy`, `Raises` branch — now
  discards the body entirely (`pass`), matching the design already applied
  to the Google-style `Raises:` header during Tier 2a: the exception class
  is always recomputed fresh from the actual `raise` statement, so there's
  nothing to merge back in, and preserving stale NumPy prose only produces
  a second, disagreeing section.
- **Verified:** `config.py`'s real `load_config` (with a real `raise`
  added for the test) now produces exactly one, correctly ordered,
  Google-style `Raises:` section. New test
  `test_numpy_raises_section_not_corrupted_on_regeneration`
  (`test_edge_cases.py`); updated `test_parse_numpy_params_and_returns`
  (`test_docstring_parser.py`), which asserted on the old fold-into-
  description behavior. 4-pass regeneration idempotent. Full suite
  111/111, Black/flake8 clean, fixture still 3-pass stable at 27
  issues/2 categories (unchanged).

### §1.4 — String forward-reference annotations resolved to `Any`

- **Finding:** `type_analyzer.py`'s `get_annotation_type` handled
  `ast.Constant` only for the `None` annotation; any other constant (i.e.
  any quoted forward reference, `-> "ClassName"`) fell through to `"any"`.
  Hit the tool's own public API: `PyCodeCommenter.from_string`/`from_file`
  both declare `-> "PyCodeCommenter"` and got `Returns: Any:` instead of
  `Returns: PyCodeCommenter:`.
- **Fix:** `type_analyzer.py:118-127` — widened the `ast.Constant` branch to
  return `annotation.value` directly when it's a `str`. Recursive, so it
  also resolves a forward reference nested inside a generic (e.g.
  `Optional["ClassName"]`) for free.
- **Verified:** tool's own `from_string`/`from_file`; fixture's
  `OrderProcessor.empty`/`Coordinates.distance_to`; `-> None` non-regression
  check. 3 new tests in `test_type_analyzer.py`. Full suite 110/110,
  Black/flake8 clean, 3-pass fixture regeneration still idempotent,
  `validate()` on regenerated fixture unchanged (27 issues, same 2
  categories).

### Idempotency bug — stale default value on source edit (follow-up gap)

- **Finding:** `_strip_own_default_annotation` matched a suffix only when
  it equaled the parameter's *current* default, so editing a default in
  source between `generate` runs (`0.1` → `0.2`) left the stale `"
  (default: 0.1)"` suffix in place alongside a freshly appended `"
  (default: 0.2)"` — the same compounding failure via a legitimate edit
  instead of a bare rerun.
- **Fix:** `commenter.py:66-71` (new `_TRAILING_DEFAULT_ANNOTATION_RE`),
  `:610-629` (`_strip_own_default_annotation`, now strips *any* trailing
  `" (default: ...)"` suffix unconditionally, since the append immediately
  below always re-adds the correct current one regardless), `:283-286`
  (call site).
- **Verified:** exact edit-then-regenerate repro from the report; 4-pass
  regeneration still stable; full fixture still 3-pass stable. New test
  `test_stale_default_value_does_not_compound_when_default_changes`
  (`test_edge_cases.py`). Full suite 107/107 at the time, Black/flake8
  clean.

### `ai_draft` validator severity

- **Finding:** the `ai_draft` category (unreviewed AI-drafted content, from
  Tier 2b) used `Severity.INFO` — lower than the `Severity.WARNING` the
  placeholder-quality check uses for a literal `TODO`, even though fluent,
  confident-sounding unverified text is at least as likely to be mistaken
  for fact.
- **Fix:** `validator.py:779` — `Severity.INFO` → `Severity.WARNING`. No
  `to_dict()` JSON schema impact (`warnings` was already a first-class
  `ValidationStats` field).
- **Verified:** severity assertion added to
  `test_ai_draft_marker_is_its_own_validator_category`
  (`test_description_provider.py`).

### Idempotency bug — default-value and `None`-return compounding

- **Finding:** `generate` was not idempotent. Every rerun on a file with a
  defaulted parameter appended another copy of `" (default: ...)"` onto
  that parameter's Args line, unbounded across reruns; a niladic function's
  `Returns:\n    None.\n` became `Returns:\n    None: None.\n` on the very
  next regeneration. Root cause: `DocstringParser` reads the tool's own
  previously-generated text back as free-form author prose, and
  `commenter.py` re-wraps it instead of recognizing its own output.
  Confirmed pre-existing (reproduces on the untouched pre-Tier-2a
  checkout).
- **Mechanism check (as required before implementing):** traced whether
  `GUESS_MARKER`'s apparent regeneration-stability (cited in the bug
  report) was a dedicated "recognize my own literal" mechanism. It isn't —
  it's a side effect of a general "strip the old type prefix if it matches
  the current type" merge step in the `Returns:` branch, which happens to
  round-trip `GUESS_MARKER` correctly only because its format always
  includes a `"type: "` prefix. Confirmed this does **not** extend to a
  parameter's `GUESS_MARKER` description with a default value (it
  compounds too) — the default-suffix bug needed its own, independent fix.
- **Fix (initial pass):** `commenter.py` — `_strip_own_default_annotation`
  (matching-current-value version, later widened, see above) for the
  Args-line suffix; explicit literal check treating a re-parsed `"None."`
  return description as absent, not preserved text, before the
  existing-description merge branch runs (falls through correctly to a
  fresh guess marker if the function has since been edited to actually
  return a value).
- **Verified:** 4 consecutive regeneration passes byte-identical on both
  shapes; full fixture 3-pass stable; edited-function-starts-returning edge
  case correctly resets rather than compounding. 4 new tests in
  `test_edge_cases.py`. Full suite 106/106 at the time.

### Tier 2b — AI-assisted drafting scaffolding

- **Built, not activated:** `description_provider.py` (new) —
  `DescriptionProvider` ABC, `FunctionContext`/`ParameterFact` (built from
  the same AST facts `Args:`/`Returns:`/`Raises:` already use),
  `NullDescriptionProvider` (default, preserves current behavior exactly),
  `UnconfiguredAIDescriptionProvider` (always raises — no model to call,
  exercises the fail-closed contract in tests only).
- **Call site:** `commenter.py` — `PyCodeCommenter.__init__` takes an
  optional `description_provider` (no CLI command passes one, so this is
  inert unless a caller opts in in code); `_draft_description_via_provider`
  fails closed to `""` on any decline or exception;
  `_build_function_context` gathers the AST facts.
- **Draft marker:** `(AI-drafted, unreviewed)` (`inference.py`), appended
  by the call site (never left to a provider to remember), recognized by
  `validator.py`'s `check_content_quality` as its own `ai_draft` category.
- **Verified:** 10 tests in `test_description_provider.py` against
  fakes/stubs (default-unchanged, marked-draft-used, validator-category,
  exception-fails-closed, decline-fails-closed, provider-not-consulted-
  when-real-description-exists). Fixture output confirmed byte-identical
  before/after — the scaffolding changes nothing by default.
- **Deliberately not built:** any CLI flag/subcommand to reach this path,
  and no live model/provider. Open decision, not a bug — see below.

### Tier 2a — real facts the generator was discarding

- **2a.1 — Class `Attributes:` through real inference.** Every attribute
  got an unconditional `TODO(pycodecommenter): describe`, even though the
  same name/type signal `Args:` already used was sitting right there.
  Fixed: `commenter.py`'s `_generate_class_docstring` now calls
  `_get_parameter_description` per attribute, same as `Args:`. Verified
  against `OrderProcessor.customer_id`/`items`/`total`,
  `Coordinates.latitude`/`longitude`/`label`, `ConfigError.message`/
  `original`. Noted one discrepancy from the task's literal spec:
  `OrderProcessor.total`/float attributes with no name pattern get the
  generic `"float value."` type-fallback (same tier a same-typed, unnamed
  *parameter* already gets), not `TODO` — flagged as intentional
  consistency, not silently overridden.
- **2a.2 — `Raises:` from actual `raise` statements.** The generator only
  ever wrote `Args:`/`Returns:`/`Yields:`. New `_get_raised_exceptions`
  (`commenter.py`) walks the function's own scope (`walk_own_scope`),
  collects `ast.Raise` nodes whose `.exc` is a `Call`, skips bare `raise`
  and `raise err` (can't be resolved without data-flow analysis), renders
  an `ast.Attribute`-style raise as its short name. **Bonus fix this
  exposed:** `docstring_parser.py` didn't recognize `Raises:` as a
  Google-style header, so re-running `generate` on already-Raises-
  documented output glued the Raises block onto `Returns:` — the same
  corruption shape as the pre-existing NumPy-`Raises` bug (§1.3, closed
  separately below). Fixed by adding `Raises` to both
  header regexes in `docstring_parser.py`. Verified idempotent across
  reruns; `validate()`'s "no Raises section" warning gone with no new
  warning categories introduced.
- **2a.3 — Widened `inference.py` name-pattern vocabulary.** Added
  `id`/`*_id`, `name`/`*_name`, `key`/`*_key`, `index`/`idx`,
  `config`/`configuration`/`settings`/`options`, `result`/`output`, via a
  new `_name_ending_in` helper. Checked last, after all existing rules, so
  `*_path`/`is_`/`has_`/`can_`/`count`/`num` keep priority — verified no
  shadowing (`config_path` still hits `*_path` first, etc.). Doctests
  added.

### AUDIT_REPORT.md §1.1 / §1.2 — phantom description paragraph, chopped multi-line summary

- **§1.1 finding:** merging into an already-complete docstring (summary +
  `Args:` + `Returns:`, no separate description paragraph) injected an
  unwanted `TODO(pycodecommenter): describe` paragraph — reproduced on the
  maintainer's own "leave this alone" fixture case (`slugify`). Root cause:
  `commenter.py:187` treated "no parsed description" as "description
  missing" unconditionally.
- **Fix, in two passes:** first pass only stopped injecting the guess
  marker when merging into an *existing* docstring (`existing_doc is not
  None`); a second pass (after re-testing on real fixture output and
  finding the fresh-generation case was still ~40% of all TODO noise in a
  16-function test file) removed the guess marker from the description
  slot entirely, for both merge and fresh generation — a fresh function's
  summary is itself name-derived, so a second "nothing to add" paragraph
  under it added no information. Per-field placeholders (`Args:`/
  `Returns:`/`Attributes:`/`Methods:`) unaffected.
- **§1.2 finding:** a hand-wrapped summary spanning multiple physical
  lines with no blank line between them got split at the wrap point into a
  truncated summary plus a spurious mid-sentence description fragment
  (`param_utils.py`'s `_walk_until` reproduced this in the project's own
  source).
- **Fix:** `docstring_parser.py`'s `parse()` now takes the whole first
  paragraph (up to the first blank line or a recognized section header) as
  the summary, joined into one line — with a special case for a docstring
  that starts directly with a section header (empty summary, not the
  header text itself).
- **Verified:** `slugify` now reproduces byte-identical; `_walk_until`-style
  wrapped summary preserved as one sentence. On the real dogfood fixture:
  raw `TODO(pycodecommenter)` count 48 → 29 (the first, narrower fix)
  → confirmed via re-test this was the single largest category (19 of 48).

---

## Still open (from `AUDIT_REPORT.md`)

None — every numbered finding from the original audit is closed as of this
entry. Anything found after this point (Tier 2a/2b work, the idempotency
bug thread) is tracked in its own section above.

## Open decision, not a bug

- Tier 2b's live model wiring: which provider, API key handling, and the
  cost/latency/rate-limit implications of a real run. Deliberately left
  for the maintainer to decide explicitly — nothing in this log implements
  or defaults any of it.
