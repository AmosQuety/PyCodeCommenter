# PyCodeCommenter — Work Plan (Post-v2.5.0)

> Written after the v2.5.0 release cycle (nested-scope AST fixes, negative
> defaults, coverage crash, `--version`, `parameter_descriptions.py`
> removal). Consolidates the existing `Future Work/` documents against
> what's actually shipped now, so the next session doesn't have to
> re-derive status from scratch. Where a doc listed below is still the
> authoritative source for implementation detail, this plan points to it
> rather than repeating it.

---

## Where things stand

v2.5.0 is released. Every item from the two prior audits
(`Vulnerabilties.md`, `More future work prompt.md`) is resolved except the
two deliberate "no action" calls below. The validator/generator
nested-scope AST-walk bug class (misattributing a nested function's
return/raise, or a nested class's `self.x=`, to the outer scope) is fixed
and shared via `param_utils.walk_own_scope`/`walk_skipping_nested_classes`.

**Decisions already made, not open questions:**
- PEP 604 unions (`int | str`) render as `Union[int, str]` — kept as-is,
  intentionally, per `python-api.md`. Don't revisit without a concrete
  reason.
- `parameter_descriptions.py` is deleted. `inference.py` is now the only
  parameter-description source. Don't re-add a static per-function
  override dict without a real design for it (see the "extensibility"
  note under v3.0.0 below — that's the more likely home for this kind of
  need, if it resurfaces as user-facing config rather than a hardcoded
  dict).

---

## Small, immediate backlog

- **`--version`/`--help` trigger a `.pycodecommenter.yaml` config-load
  attempt before argparse handles them.** Found during the v2.5.0
  pre-release review; pre-existing (not introduced by v2.5.0's changes) —
  `--help` had it too, `--version` just inherited it. A malformed config
  file prints a `Warning:` line ahead of the version string, which is a
  papercut, not a bug. Fix: move `load_config()` after argparse resolves
  `--version`/`--help`, or special-case `sys.argv` before constructing the
  parser. Small, contained, no test-breaking risk.

---

## Next milestone: v3.0.0 — Safe, Configurable, Extensible

Full implementation spec: `Future Work/v3.0.0 — Safe, Configurable, Extensible.txt`.
Two features, budgeted 3-4 weeks in `Future Release WorkPlan.txt` for the
merge algorithm alone — this is the largest single piece of work on the
roadmap.

1. **Smart docstring merge** (`DocstringMerger`, new `merger.py`). Today,
   `get_patched_code()` regenerates missing sections but doesn't
   distinguish "the human wrote this" from "this looks like what the
   generator would have produced, so it's safe to refresh." The spec's
   approach (parse existing → generate fresh → section-by-section merge,
   preserving anything that doesn't match the auto-generated template) is
   still the right shape. Before starting: re-read `commenter.py` fresh —
   it's changed materially since this spec was written (the
   `param_utils` primitives, `_infer_param_type`, the CST patcher didn't
   exist or looked different at spec-writing time), so the spec's
   "MANDATORY FIRST STEP" file-reading list is still correct in spirit
   but the actual code it describes has moved on.
2. **NumPy/Sphinx *output* generation** (parsing both already works;
   generating in those styles doesn't). Gated on the `style` config key,
   which `config.py` already loads but nothing reads yet
   (`configuration.md` documents this gap explicitly).

**Before writing merge code:** the spec's own instruction to "define the
exact matching criteria" for auto-generated-content detection needs an
actual answer, not just a restatement of the goal. `GUESS_MARKER`-tagged
content is trivially identified (it's a literal string); everything else
(a real name/type/default-derived sentence from `inference.py`) is harder
to distinguish from hand-written prose that happens to read similarly.
Decide this explicitly before implementation, since a wrong heuristic here
either discards real user edits (data loss — the worst failure mode this
feature could have) or refuses to ever refresh anything (feature doesn't
do its job). The spec already says "if merging fails for any reason, fall
back to the existing docstring unchanged" — keep that fallback strict.

---

## Then: v3.1.0 — Integrations

Full spec: `Future Work/v3.1.0 — Integrations.txt`. Explicitly blocked on
v3.0.0 being solid first (its own "MANDATORY FIRST STEP" checks for
`merger.py`/`DocstringMerger` existing before allowing any v3.1.0 work to
start) — don't begin this out of order.

1. SARIF output (`--output-format sarif` on `validate`) for GitHub Code
   Scanning.
2. `.github/workflows/docs-check.yml` reusable workflow, `continue-on-error:
   true` on the validate step by design (spec is explicit this shouldn't
   block builds by default).
3. VS Code extension scaffold (`vscode-extension/`, TypeScript, two
   commands, marked `"preview": true`). Lowest-priority of the three —
   most speculative, no evidence of demand yet.

---

## Explicitly gated — do not build without the condition firing

Full reasoning: `Future Work/Docstring Prose Quality — Static Heuristics & AI Generation.md`.
Both items below were already fully argued through; don't re-litigate the
reasoning, only check whether the stated trigger condition has actually
fired.

- **Deeper static heuristics** (single-return-expression / thin-wrapper
  shape detection in `inference.py`). Conditional, not scheduled. Stated
  trigger: **5+ issues/discussions specifically about generated
  description quality within 6 months of shipping.**

  **Open problem found while reviewing this for v2.5.0: there is currently
  no mechanism that counts toward this threshold.** No GitHub issue
  template, no label, no automation — confirmed by checking `.github/`
  directly. As written, this gate can never fire, which defeats the point
  of having a condition instead of just saying "no." Before this
  matters in practice, decide one of:
  - Add a lightweight issue label (e.g. `prose-quality`) and check it
    periodically, or
  - Accept the gate is aspirational only and treat "no evidence either
    way" as "don't build it," or
  - Replace the condition with something that doesn't require external
    tracking (e.g. a `--suggest-heuristics-feedback` note in generated
    output pointing at an issue template).

  This is a process decision, not a coding task — flagging it here so
  it doesn't get silently forgotten the next time this document is read.

- **AI-assisted generation.** Not conditional — a considered "no" to any
  generate-and-write shape of this feature, for reasons (cost,
  hallucination risk, non-determinism breaking CI-safety, privacy, the
  project's own "no AI dependency" brand claim) that don't weaken over
  time or with better models. If ever revisited: draft-and-review only,
  modeled on Mintlify Workflows, **never** writable via `--inplace`. Any
  proposal that writes AI output the same way the deterministic path does
  is the wrong shape and should be rejected in review, not merged and
  fixed after.

---

## Lower-priority backlog (not urgent, no trigger condition)

From `Future Work/More future work.md` — directory support itself shipped
in v2.3.0; these are the extras that didn't:

- Progress reporting / per-file summary output for `generate` on a
  directory target (the proposal's `📁 Found N files... ✅/⚠️/❌` UX).
- `.gitignore`-aware exclusion (`use_gitignore: true` config key) as an
  alternative/addition to the current explicit `exclude` list.
- Parallel processing for large directory trees.
- Interactive mode (selective per-file confirmation before writing).

None of these have a specific trigger condition — pick them up
opportunistically, or when a real user asks for one specifically, rather
than building speculatively.

---

## Suggested order

1. Small backlog item (`--version`/`--help` config-load ordering) — cheap,
   isolated, do it whenever convenient.
2. v3.0.0 smart merge + multi-style generation — the big piece, only start
   with real time budgeted (3-4 weeks per the original estimate) and after
   re-reading the current `commenter.py`/`docstring_parser.py` fresh, not
   from memory of the original spec.
3. v3.1.0 integrations — after v3.0.0 ships and is stable, in the order
   SARIF → GitHub Actions workflow → VS Code extension (matches both the
   spec's own dependency note and descending confidence that each is
   actually wanted).
4. Static heuristics / AI generation — leave alone until their respective
   conditions are resolved (see above). Don't schedule work here by
   default.
