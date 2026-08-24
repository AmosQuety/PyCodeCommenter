# PyCodeCommenter — Docstring Prose Quality: Static Heuristics & AI Generation

> Written by: Claude (Sonnet 5)
> Codebase version: v2.4.0 · Written directly after the Phase 7-13 review cycle
> (shared parameter-extraction fix, GUESS_MARKER, doctest CI, coverage badge,
> README/docs sync, v2.4.0 release prep)

---

## Context — Why This Document Exists

v2.4.0 closed two separate defects in what the generator's Args/Returns/Attributes
extraction actually *sees*, and in what it's honest about not knowing.

The first defect was structural: `func_node.args.args` was the sole source of
truth for "this function's parameters" in three independent call sites, so
keyword-only params, positional-only params, `*args`/`**kwargs`, and
`self.x = ...`/`@dataclass` class attributes were silently invisible to both
generation and validation. `param_utils.get_all_parameters()` fixed that —
it's a correctness bug with a correct, deterministic fix, and there's nothing
more to decide about it.

The second defect was honesty, not structure: the generator was writing
guessed content — "Description of the return value.", "[describe purpose]",
"Executes the function X." — as if it were finished prose, with nothing
distinguishing an extracted fact (a parameter's name, type, default) from a
guess (what that parameter or function actually *means*). `GUESS_MARKER`
fixed the presentation problem: guesses are now an explicit, greppable
`TODO(pycodecommenter): describe` instead of a grammatically complete
sentence that looks done.

Neither fix makes the DESCRIPTION TEXT itself any better. They make the tool
honest about the fact that it can't currently write that text at all. That
honesty immediately raises the next question — a legacy-codebase user who
runs `generate --inplace` across 400 functions now gets 400 correct
skeletons and 400 honest TODO markers instead of 400 confidently wrong
sentences, which is strictly an improvement, but doesn't reduce the amount
of prose a human still has to write. This document is about that next
question: how the prose itself could get better, and — for the option that
would answer it fastest — why that option was deliberately not taken.

Two options exist. One is conditional on evidence that doesn't exist yet.
The other is constrained hard enough that "not now" undersells it — read
Item 6 as "not like this, maybe never, and if ever, only in one specific
shape."

---

## Item 5 — Deeper Static Heuristics

**Status: ⏸ CONDITIONAL — not scheduled, not rejected.**

`inference.py`'s current heuristic chain (name pattern → type hint → default
value → generic fallback, now `GUESS_MARKER`) only ever looks at a
parameter's own name, type, and default. It never looks at what the function
*does* with its body. A modest static-analysis upgrade could look at a
function's body SHAPE — still zero network calls, still zero AI, still fully
deterministic — and describe a few more cases without guessing:

- A function whose entire body is a single `return <expr>` could describe
  the expression directly (e.g. `return a + b` → "Returns the sum of `a`
  and `b`.", modulo how much the expression itself is worth spelling out).
- A function that's a thin wrapper — its body is essentially one call to
  exactly one other method or function — could say "Delegates to
  `other_func`." instead of falling back to a marker.
- Other shapes in the same spirit are plausible (a loop-plus-`yield` that
  summarizes as "Yields each item from `X`, transformed by `Y`.", a
  single-attribute-access property), but the two above are the clearest,
  lowest-risk starting points if this is ever picked up.

This raises the ceiling on template-generated prose somewhat. It does not
change the category of thing being produced: it is still pattern-matching
on code shape, not understanding intent, and every case wide of these
narrow shapes still falls back to `GUESS_MARKER`, correctly.

### Why this is conditional, not scheduled

Building this now — before anyone has used v2.4.0's honest-marker behavior
and said the markers themselves are the bottleneck — would repeat the exact
mistake that started this whole review cycle: shipping capability nobody
had asked for or verified was wanted, that turned out on inspection to be
low-quality filler nobody actually used. The original problem with this
codebase wasn't that its heuristics weren't clever enough; it was that
guessed content was presented as finished documentation without anyone
having asked "does a slightly-cleverer guess still deserve to look
finished?" More heuristics without that question answered first is the same
mistake at a different sophistication level, not a fix for it.

**Trigger condition for revisiting this** (placeholder numbers — a judgment
call, not a hard requirement from any spec): **5 or more issues or
discussions opened specifically about generated description quality within
6 months of v2.4.0 shipping.** Below that bar, the honest marker is doing
its job (making the gap visible and routing it to a human) and there's no
evidence a cleverer guess would be worth the added surface area. At or above
it, that's real signal from real usage, not a guess about what users might
want — which is exactly the standard this document is holding Item 5 to.

---

## Item 6 — AI-Assisted Generation

**Status: 🔒 CONSTRAINED — do not build as generate-and-write, under any
circumstances, on anyone's judgment call. If ever revisited, draft-and-review
only.**

### The decision

Do not build AI-assisted description generation as a feature that writes
output a user can apply with `--inplace`. This is not "deprioritized" or "not
yet" — it's a standing constraint on the *shape* any future work in this
area is allowed to take, decided after a full costs/benefits review, not an
oversight waiting to be picked up by whoever gets to it next.

### The reasoning, in full

This has existed scattered across the README's Roadmap blockquote and prior
analysis sessions. Consolidated here as the canonical, complete version:

- **Cost is real and recurring, not one-time.** A `pip install` is a fixed
  cost paid once. An LLM call per function, per run, is a cost that scales
  with function count × run frequency, forever, for every user, on every CI
  run. That's a fundamentally different economic shape than everything else
  this tool does.

- **Accuracy is not solved by routing the problem through an LLM.** An LLM
  reading one function's source in isolation has no more real understanding
  of the codebase's intent than a fast human skim of the same function would
  — it can state the obvious (restate the signature in prose) and miss the
  actual non-obvious behavior worth documenting, and it can hallucinate
  outright: invented constraints, invented side effects, invented
  guarantees the code doesn't actually provide. This isn't a "current
  models aren't good enough yet" problem that improves with a better model;
  it's a structural limit of judging intent from one function's text with no
  access to the surrounding system, the actual runtime behavior, or the
  author's real intent.

- **The failure mode is worse than the current TODO marker, not better.**
  Confident, fluent, wrong prose is more likely to be trusted without
  verification than an obviously-incomplete placeholder is — that's the
  entire mechanism by which hallucinated documentation does damage. A marker
  that says "unreviewed" only helps if someone actually checks it, and
  realistically most won't, the same way lint warnings stop getting read
  once there are enough of them. Replacing "obviously unfinished" with
  "looks finished, might be wrong" is a regression dressed as progress.

- **Non-determinism breaks the property that makes this tool CI-safe.** The
  same unchanged function could produce different wording on different
  runs, with no way to write an exact-match regression test against
  correctness — only "did something get generated," which is a much weaker
  guarantee than what this tool provides everywhere else. Every other check
  in this codebase (signature match, type consistency, coverage) is
  byte-for-byte reproducible given the same input; this would be the one
  exception, and it would be the one exception in the exact place — CI
  gating — where reproducibility matters most.

- **Privacy: function bodies would leave the machine.** Sent to a
  third-party API, regardless of how carefully opt-in is designed. This
  disqualifies the feature outright for confidential or regulated code, and
  "it's opt-in" doesn't fix that for a user who can't tell in advance which
  functions are sensitive before they're processed.

- **Brand cost.** This project's stated design pillar (see `CLAUDE.md` and
  the README's own framing) is "no network calls, no AI/LLM dependency."
  Any code path that CAN call an LLM — even opt-in, even off by default —
  changes that claim from "structurally cannot" to "won't unless asked to."
  That's a materially weaker guarantee, and it's weaker for exactly the
  audience (CI-strict, security-conscious teams) that chose this tool
  *because* of the stronger one. A guarantee that degrades from "impossible"
  to "policy" is a different, lesser guarantee, even if the policy is never
  violated in practice.

### The constraint, if this is ever revisited

Stated as non-negotiable, matching the README Roadmap blockquote and the
persisted decision exactly: **AI output must never be writable via
`--inplace`.** It may only ever be emitted as a diff or preview that a human
deliberately applies — never a direct write, never a default-on path, never
"trust the model, review later." A plain "generate docstrings with AI"
implementation that writes on `--inplace` the same way the deterministic
path does is explicitly the wrong shape for this feature and should be
rejected in review, not merged and fixed afterward.

This isn't an invented extra-cautious constraint unique to this project —
it's how the actual best-in-class tool in this space already operates.
Mintlify's "Workflows" agent drafts documentation updates from a diff, opens
a pull request, and never publishes directly. If AI-assisted generation is
ever built here, that's the precedent to match, not a hypothetical ideal.

---

## Cross-References

The README's Roadmap section (the struck-through
`~~Optional AI-powered description generation~~` line and its warning
blockquote) carries a condensed version of Item 6's constraint — enough to
stop a skimming reader from treating it as an open, unclaimed feature, but
not the full reasoning. **This document is the canonical, complete version.**
If the two ever read as saying different things, this document is the one
that's right, and the README's blockquote should be updated to match it —
not the other way around.

---

## Bottom Line

Item 5 is a real, bounded, low-risk improvement that stays inside this
project's deterministic-AST identity — it's just not worth building on
spec before anyone has said the current honest markers are the actual
bottleneck. Item 6 is not a scheduling question at all: it's a considered
"no" to one specific shape of feature (generate-and-write), for reasons that
don't get weaker as models improve, with an explicit, narrower shape
(draft-and-review, modeled on Mintlify Workflows) that remains open if
anyone wants to make the case for it later. Neither item is a bug-tracker
item. Both are here so the next person who has this idea reads this first,
instead of re-deriving — or worse, re-shipping — a version of the exact
mistake v2.4.0 just finished cleaning up.
