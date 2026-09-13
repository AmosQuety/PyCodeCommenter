# AI Backend Implementation Plan

Onboarding + implementation plan for the hosted AI-drafting backend. If
you're new to this thread: read this top to bottom before touching code.
Section 3 tells you what already exists; sections 5 onward are the actual
build plan, not yet implemented.

---

## 1. What PyCodeCommenter is

A deterministic, AST-based Python docstring generator and validator
(published to PyPI as `pycodecommenter`). It reads a function's real
signature — parameter names, static types, defaults, return type, raised
exceptions — and generates a Google-style docstring from those facts. It
also validates existing docstrings against the actual code (catching drift)
and measures documentation coverage. Historically: no network calls, no
AI/LLM dependency. Everything correct about the tool comes from actually
reading the code with the stdlib `ast` module, not from guessing.

## 2. Why AI, and why not sooner

An internal dogfooding audit (`Another_Test_PyCodeCommenter/Feedback/
AUDIT_REPORT.md`) found the tool's own honest ceiling: AST facts can say
*what type* a value is, never *what it means*. `calculate_discount`'s
`rate` parameter gets "float value." — true, and useless. A human would
write "the discount percentage to apply." That gap is structural, not a
bug — no amount of better AST pattern-matching closes it.

The project's own prior write-up (`Future Work/Problem and solution.txt`)
already reasoned through this and explicitly declined to paper over it with
fake prose. Two fixed generations of that discipline exist in the codebase
today:

- **Tier 1** (already shipped before this thread started): stopped writing
  confident-sounding lies ("Executes the function X.") for things the tool
  couldn't know, replacing them with a literal, greppable
  `TODO(pycodecommenter): describe` marker instead.
- **Tier 2a** (this thread): extracted more *real* facts the generator was
  discarding — routed class attributes through the same inference `Args:`
  already used, generated `Raises:` from actual `raise` statements, widened
  the name-pattern vocabulary (`customer_id` → "Unique identifier for the
  customer.").
- **Tier 2b** (this thread): the AI-drafting scaffolding, built and
  approved in two stages specifically to prevent AI from becoming a second
  version of Tier 1's original mistake. The non-negotiable principle stated
  at the start of that task and still true today:

  > Do not reduce the `TODO(pycodecommenter): describe` count by writing
  > prose that looks like a real answer but isn't grounded in anything.

  Every design decision below inherits from that sentence. If you're
  tempted to relax a constraint to make AI drafting more convenient, that's
  the sentence to re-read first.

## 3. What's already built (current state)

All of this exists in the `PyCodeCommenter` repo today, tested, and
verified against a real Gemini account. None of it is committed to git yet
as of this document.

### 3.1 The pluggable interface (`PyCodeCommenter/description_provider.py`)

- `DescriptionProvider` — an ABC with one method,
  `draft_function_description(context: FunctionContext) -> Optional[str]`.
  `None` means "decline"; the call site treats a decline and a raised
  exception identically — both fail closed to today's behavior (empty
  description slot, no fabricated text).
- `FunctionContext` / `ParameterFact` — the AST facts a provider drafts
  from: function name, parameters (name/type/default), return type,
  `is_generator`, raised exceptions, and the function's own source text.
  A provider never sees just a name — it sees what the code actually does.
- `NullDescriptionProvider` — the default. Always declines. This is what
  every `PyCodeCommenter()` instance uses unless a caller explicitly passes
  a different provider.

### 3.2 The direct-to-Gemini implementation (`PyCodeCommenter/gemini_provider.py`)

`GeminiDescriptionProvider` — a real, working `DescriptionProvider`.
Built against a reference multi-provider chat orchestrator
(`~/dev/react/Portfolio/portfolio/src/lib/ai-orchestrator`) for the
failover *shape* only — that reference's chat/streaming/tool-loop/
telemetry machinery is irrelevant to our one-shot "describe this function"
call.

- **Multi-key failover.** Takes a list of API keys
  (`GEMINI_API_KEYS`, comma-separated). Each key has its own circuit
  breaker: closed → open immediately on HTTP 429 (quota) or after 2
  consecutive other failures → 60s cooldown → half-open probe. A request
  tries each non-open key in order; a non-429 failure gets one retry
  before moving to the next key; every key exhausted → `None`.
- **Model discovery, not a hardcoded name.** `model=None` (default)
  queries `GET /models` per key, prefers a Google-maintained `-latest`
  alias, falls back through non-preview "flash" models, then any flash
  model, then a constant only if discovery itself fails. Cached 5 minutes
  per key. This exists because the first hardcoded default
  (`gemini-2.0-flash`) was confirmed, live, to no longer exist by the time
  it was tested — model names in this API churn fast enough that hardcoding
  one is a bug, not a shortcut.
- **The "thinking budget" fix.** Some current Gemini models default to
  spending their entire output-token budget on invisible internal
  reasoning before writing anything, especially on this API's newer
  models — the first live end-to-end test came back truncated mid-sentence
  because of this. Fixed with `generationConfig.thinkingConfig.
  thinkingBudget: 0` (a one-sentence description needs no extended
  reasoning), which also cut real token usage ~4x.
- **`max_calls`.** Caps real API calls per provider instance, checked
  before every individual attempt. Insurance against a large `generate`
  run silently burning a free-tier daily quota.
- **`from_env()`.** Loads `.env` via `python-dotenv` (the `[ai]` extra's
  only new dependency), searching from the *process's* working directory
  (not the package's install location — an earlier version of this
  accidentally searched from the wrong place and silently loaded the real
  project `.env` from an unrelated directory during a test, causing 8
  unintended live API calls; now fixed and covered by a test).

### 3.3 Generator wiring (`PyCodeCommenter/commenter.py`)

- `PyCodeCommenter.__init__(description_provider=None, ...)` — opt-in only.
  No CLI command passes one by default; a caller must construct it
  explicitly.
- `_build_function_context(func_node)` — builds a `FunctionContext` from
  the same primitives `Args:`/`Returns:`/`Raises:` generation already uses.
- `_draft_description_via_provider(func_node)` — the fail-closed wrapper.
  Any exception, `None`, or empty string from the provider all resolve to
  `""` (today's behavior). On success, appends the permanent
  `(AI-drafted, unreviewed)` marker — the *call site* does this, never the
  provider, so a future provider implementation can't forget it.

### 3.4 Validator recognition (`PyCodeCommenter/validator.py`)

`check_content_quality` recognizes the `(AI-drafted, unreviewed)` marker as
its own `ai_draft` category, `Severity.WARNING` (raised from `INFO` — the
maintainer's call: fluent unverified text is at least as likely to be
mistaken for fact as a literal TODO, so it shouldn't rate lower severity).
Never silently counted as "documented," never conflated with the TODO
placeholder category.

### 3.5 CLI (`PyCodeCommenter/cli.py`)

- `generate --ai-draft` — turns the provider on for this run. Errors
  clearly if no keys are configured.
- `generate --accept-ai-drafts` — required *in addition to* `--ai-draft`
  only when combined with `--inplace` (writing straight to source).
  `--dry-run`/`--output-dir` need `--ai-draft` alone, since both are
  already review-first, non-destructive paths.
- `generate --max-ai-calls N` — default 20 when `--ai-draft` is used
  without it; `0` for unlimited.
- **One shared provider instance per CLI invocation**, not rebuilt per
  file — otherwise circuit-breaker state and the call-count cap would
  reset on every single file in a directory run, defeating their purpose.

### 3.6 Test coverage

161 tests passing across the whole suite. AI-specific: 26 in
`test_gemini_provider.py` (failover, retry, circuit-breaker persistence,
`max_calls`, prompt grounding, `from_env`, 10 on model discovery
specifically) + 7 in `test_cli.py` (flag gating, shared-instance-not-
per-file). One dedicated test,
`test_gemini_provider_marked_and_categorized_through_full_pipeline`,
proves the marker/validator scaffolding survives contact with the real
provider (network mocked), not just a hand-written stub — this was an
explicit requirement, not left implied by the others passing. Zero live
network calls in the automated suite; live end-to-end verification was
done manually against a real account, twice (once before and once after a
key rotation — see the incident note in `Future Work/Audit Remediation
Log.md` if you want the full story of an API key that briefly leaked into
a terminal output and was rotated as a precaution).

## 4. Why we're adding a hosted backend now

`--ai-draft` today requires the *person running the CLI* to have their own
`GEMINI_API_KEYS` configured. That's correct and stays correct as a
supported mode — but it means anyone who installs `pycodecommenter[ai]`
from PyPI and runs `--ai-draft` cold gets an error until they go get their
own Gemini keys. PyPI itself has no equivalent of Vercel/Render/Netlify's
environment-variable injection, and structurally can't: PyPI distributes
packages, it doesn't execute them. Whoever's machine runs the installed
code is the only "runtime" that exists, so secrets have to live wherever
that person's `.env`/environment already does — there's no shared runtime
to inject them into centrally.

Decision: run a small proxy service (this maintainer's own Render-hosted
backend, free tier) that holds the real keys server-side. The CLI talks to
the proxy instead of Gemini directly when the user has no keys of their
own. This is a deliberate trade: real infrastructure and ongoing hosting
responsibility, in exchange for `--ai-draft` working out of the box for
anyone who installs the tool.

## 5. New architecture

```
                    (no local Gemini keys)
PyCodeCommenter CLI ────────────────────────► Render-hosted Flask proxy ───► Gemini API
        │                                          (holds the real keys,
        │  (local GEMINI_API_KEYS present)          rate limiting, daily cap)
        └──────────────────────────────────────────────────────► Gemini API
                                                     (direct, unchanged)
```

Precedence, decided in the planning conversation: **local keys present →
call Gemini directly (existing `GeminiDescriptionProvider`, unchanged);
local keys absent → fall back to the hosted proxy automatically**
(`RemoteDescriptionProvider`, new). An explicit override flag lets someone
force either path regardless of what's locally configured. This keeps
power users off the shared service by default (their own quota, their own
control) and makes the zero-config case just work.

## 6. Backend implementation plan (Flask)

### 6.1 Repo

**Separate repo**, not a subdirectory of `PyCodeCommenter`. Different
dependency set (a web framework, a WSGI server), different deploy
lifecycle (Render deploys from its own repo/branch, independent of PyPI
release timing), and it guarantees server code and Render config can never
accidentally end up in the PyPI sdist/wheel. Working name in this doc:
`pycodecommenter-ai-backend` — pick the real name when the repo is created.

### 6.2 Dependency reuse — the key design decision

The backend depends on `pycodecommenter[ai]` (this project, published) as
an ordinary dependency and imports `GeminiDescriptionProvider` directly:

```python
from PyCodeCommenter.gemini_provider import GeminiDescriptionProvider
from PyCodeCommenter.description_provider import FunctionContext, ParameterFact
```

No key-rotation, circuit-breaker, model-discovery, or thinking-budget logic
gets reimplemented in the backend. One source of truth for "how to call
Gemini reliably" — this codebase. If that logic changes here, the backend
picks it up on its next dependency bump, not via a second, drifting copy.

### 6.3 Endpoint contract

One versioned POST endpoint:

```
POST /v1/draft-description
Content-Type: application/json

{
  "name": "calculate_discount",
  "parameters": [
    {"name": "price", "type_hint": "float", "default": null},
    {"name": "rate", "type_hint": "float", "default": "0.1"}
  ],
  "return_type": "float",
  "is_generator": false,
  "raised_exceptions": [],
  "source": "def calculate_discount(price, rate=0.1):\n    return price * (1 - rate)"
}
```

Response, success:

```json
{"description": "Calculates the discounted price by applying rate to price."}
```

Response, decline/failure (still HTTP 200 — this is an expected outcome,
not a server error):

```json
{"description": null}
```

Response, rate-limited or daily cap reached: HTTP 429, with a `Retry-After`
header and a short JSON body naming which limit was hit — the client needs
to distinguish this from "the whole service is down" so it can fail
closed cleanly rather than retrying pointlessly against a service that has
explicitly said no for the day.

The contract is intentionally Gemini-agnostic on the wire (no model names,
no Gemini-specific fields cross this boundary) — the client asks for "a
description," not "a Gemini completion." If the backend ever switches or
adds providers server-side, no client update is required.

### 6.4 Flask app shape

```
app.py                 # Flask app factory, route registration
config.py              # env-driven settings (keys, rate limits, daily cap)
routes/
  draft.py             # POST /v1/draft-description handler
middleware/
  rate_limit.py         # Flask-Limiter setup (per-IP)
  daily_cap.py           # global call counter + reset logic
requirements.txt        # flask, pycodecommenter[ai], flask-limiter, gunicorn
Procfile / render.yaml  # Render deploy config
```

- **Rate limiting**: `Flask-Limiter`, per-IP, something like "10 requests
  per minute" as a starting point — cheap to add, blocks casual/accidental
  misuse (a fuzzer, a runaway loop in someone's script). Not a real
  defense against a deliberate abuser (see 6.6), just noise reduction.
- **Daily cap**: a simple in-memory counter (`threading.Lock`-guarded
  int), reset on a UTC-midnight check. Configurable via an env var
  (`MAX_DAILY_CALLS`). Honest limitation for v1: this resets on every
  redeploy/cold-restart, so it's not a hard cross-day guarantee on Render's
  free tier — acceptable given the actual stakes here (worst case: the
  free proxy stops answering for the rest of a day, never a cost surprise,
  since nothing paid is at risk).
- **Logging**: metadata only — timestamp, latency, outcome (success/
  decline/error), maybe a truncated function name for debugging. **Never
  log the `source` field or the drafted description text.** Logging
  request bodies would make the backend a second, persistent copy of every
  caller's source code sitting on a server they don't control — exactly
  the kind of scope creep the privacy notice (section 8) exists to prevent
  from happening silently.
- **Health check**: a trivial `GET /health` returning 200, both for
  Render's own health monitoring and as something the client could
  optionally ping to pre-warm a sleeping instance (see 6.5).

### 6.5 Render deployment specifics

- Free-tier web services sleep after ~15 minutes of inactivity; the next
  request pays a cold-start cost (can be tens of seconds). This has to be
  designed for on the client side (section 7), not assumed away.
- Set `GEMINI_API_KEYS` as a Render environment variable (Render's
  dashboard has exactly the kind of "environment variables" section the
  original question was about — that's the right place for the real keys
  now, since the backend *is* a long-running service, unlike PyPI).
- Start command: `gunicorn app:app` (or Flask's own dev server is fine to
  prototype with, but gunicorn for anything actually deployed).
- No persistent disk needed for v1 given the in-memory daily-cap decision
  above; revisit if that limitation becomes a real problem in practice.

### 6.6 Abuse/cost posture — stated plainly, not glossed over

There is no real authentication on this endpoint. Anyone can read the
`RemoteDescriptionProvider` source in the public PyPI package, see the
backend URL, and call it directly with a script — a bearer token baked
into an open-source client provides no protection against that, since the
token would be just as public as the URL. The actual mitigations (per-IP
rate limiting, a global daily cap, no cost exposure since Gemini's free
tier is $0) are sized to match that reality: they bound the *nuisance* a
bad actor can cause (the shared proxy going quiet for a day) without
pretending to be a security boundary they aren't. If usage patterns later
suggest this isn't enough, that's a "revisit then" problem, not a "block
launch on solving it now" problem, given the actual stakes.

## 7. Client-side implementation plan

### 7.1 New provider (`PyCodeCommenter/remote_provider.py`, or added to
`gemini_provider.py` — pick when implementing; a separate module is
probably cleaner since this one has no Gemini-specific knowledge at all)

```python
class RemoteDescriptionProvider(DescriptionProvider):
    def __init__(self, backend_url: str, timeout_s: float = 90.0):
        ...

    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        # Serialize FunctionContext -> the JSON contract in 6.3.
        # POST with a generous timeout (Render cold starts).
        # 200 with description -> return it.
        # 200 with null, 429, timeout, network error, malformed response
        #   -> None. Never raise past this boundary for an expected
        #   failure mode (same fail-closed contract as GeminiDescriptionProvider).
```

`timeout_s=90.0` default, specifically because of Render's cold-start
behavior — 15s (the direct-Gemini default) would false-fail on a sleeping
instance's first request of the day.

### 7.2 Selection logic (where the precedence from section 5 actually lives)

Likely in `cli.py`, alongside the existing `--ai-draft` handling: attempt
`GeminiDescriptionProvider.from_env()` first; if it raises `ValueError`
(no local keys), fall back to constructing `RemoteDescriptionProvider`
pointed at a built-in default backend URL (a constant, or an env var
`PYCODECOMMENTER_AI_BACKEND_URL` override for testing against a staging
deploy). An explicit `--ai-provider=local|hosted` flag can force either
path, mainly useful for testing and for someone who wants to guarantee
they're never touching the shared service.

### 7.3 Consent flow

Per the planning decision: **one-time, explicit consent**, gated on a
versioned notice, before any code is sent to the hosted backend.

- A small local state file, e.g. `~/.pycodecommenter/consent.json`
  (per-user/per-machine, deliberately outside any project directory —
  this is a decision about the person, not about any one codebase they run
  the tool against).
- Stores something like `{"hosted_ai_consent_version": 1}`.
- The notice text gets its own version number; if what gets sent or
  logged server-side ever materially changes, bump the version so
  previously-given consent doesn't silently carry over to different terms.
- First hosted-mode use with no matching consent on file: print the full
  notice (what's sent — the function's source code — and where it goes —
  a proxy this maintainer runs, then Google's Gemini API) and require an
  explicit yes (interactive prompt, or a `--yes-send-code-to-hosted-ai`
  flag for non-interactive/CI use) before the request goes out. Once
  given, write the consent file and don't ask again until the version
  bumps.

## 8. Privacy notice — actual draft language to refine at implementation time

> PyCodeCommenter is about to send this function's source code to a
> hosted service (run by the PyCodeCommenter maintainer) and then to
> Google's Gemini API, to draft a description. No source code is stored
> beyond the time it takes to process this request. Continue? [y/N]

Refine wording during implementation, but keep the two facts explicit:
*whose* server it transits (not the user's own Gemini account) and *what*
leaves the machine (the function's actual source, not just its name).

## 9. Testing strategy

- **Backend**: standard Flask test client, mocking `GeminiDescriptionProvider`
  (or its `_post`) so backend tests never make live calls either — same
  discipline as this repo's own test suite. Cover: happy path, decline
  path, rate-limit response, daily-cap response, malformed request
  rejection.
- **Client**: `RemoteDescriptionProvider` tests mock the HTTP layer the
  same way `GeminiDescriptionProvider`'s tests mock `_post` — no real
  network calls in the automated suite. Cover: success, decline, timeout,
  429, malformed response, and the precedence logic (local keys present
  vs. absent) in `cli.py`.
- **One manual, real end-to-end run** against the actual deployed Render
  instance before considering this shippable — the same discipline applied
  to `GeminiDescriptionProvider` (which caught 4 real bugs no mock would
  have found) applies at least as much here, since a cold Render instance
  behaves nothing like a mock.
- **Consent flow**: test the state file's read/write/version-mismatch
  behavior directly; don't rely on manually clearing `~/.pycodecommenter/`
  between test runs.

## 10. Suggested rollout sequence

1. Stand up the backend repo, deploy a minimal version to Render, confirm
   the `/v1/draft-description` endpoint works against a real Gemini call
   (manually, via curl) before writing any client code against it.
2. Build `RemoteDescriptionProvider` and its tests against that live
   deployment (or a local mock of it).
3. Build the consent flow and its tests.
4. Wire the precedence logic into `cli.py`.
5. One full manual end-to-end run: fresh environment, no local keys, run
   `generate --ai-draft --dry-run`, confirm the consent prompt, the cold-
   start behavior, and a correct drafted+marked description.
6. Only then consider flipping `--ai-draft`'s hosted path on by default
   for users with no local keys — everything before this point can be
   built and verified without changing any existing user's behavior.

## 11. Open questions — not yet decided, flag before implementing

- Exact Render service name/URL (needed as the client's default backend
  URL).
- Whether the daily cap should eventually move to a small persistent store
  (e.g. a free-tier Redis) instead of in-memory, once real usage patterns
  are known.
- Exact per-IP rate limit numbers (starting guess: 10/minute — adjust once
  there's real traffic to look at).
- Whether `--ai-provider=local|hosted` is the right flag name/shape, or
  whether precedence alone (no override) is simpler and sufficient for v1.
