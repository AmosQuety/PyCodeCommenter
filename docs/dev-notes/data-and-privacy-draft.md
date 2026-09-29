# Data and privacy (DRAFT for the docs site)

Status: draft written from what the code does (`ai_drafting.py`,
`commenter.py`, `secret_scan.py`, `consent.py`, `remote_provider.py`,
`direct_providers.py`, `ai_setup.py`). It is not in the docs nav. Every
`[PLACEHOLDER]` is something the code cannot show and needs an answer from the
maintainer before this page is published. Nothing here describes how the
hosted backend stores data.

---

## The short version

- PyCodeCommenter sends nothing anywhere unless you pass `--ai-draft` (or use
  an AI provider from the Python API). `generate` without it, `validate`,
  `coverage` and `review` make no network calls.
- With `--ai-draft`, the source of the functions and classes that have gaps is
  sent to one service that you choose, after you agree once per destination.
- You choose between PyCodeCommenter's hosted service and your own key with a
  vendor (Gemini, OpenAI, Anthropic, DeepSeek, or any OpenAI-compatible
  endpoint). Your key is never sent to the hosted service.

## What is sent

For each function that has a gap, one request carrying:

| Item | Detail |
|---|---|
| The function's name | |
| Its parameters | name, inferred type, default value as written |
| Return type, whether it is a generator, exceptions it raises | read from the code |
| **The function's source** | from the `def` line to its last statement, **including its docstring and any comments inside the body**. Decorators and comments above the `def` are not included |
| Text already settled | your existing parameter, return and exception descriptions, so the draft stays consistent |
| Which parts are wanted | for example summary, parameter `x`, return |

For each class that has a gap: its name and base classes, its attributes with
types, and an **outline** (the class line, class-level statements, `__init__`
in full, and every other method as its signature only), plus your existing
attribute text.

Not sent: functions and classes with nothing to draft, the rest of the file,
other files, module docstrings, and your file names and paths (the hosted
request body has only `name`, `parameters`, `return_type`, `is_generator`,
`raised_exceptions`, `source`, `known` and `slots`; for classes `name`, `bases`,
`attributes`, `source`, `known` and `slots`). Your API key goes only to the
vendor it belongs to.

## What is filtered first

Before a function or class is sent, `secret_scan.looks_like_secret` checks its
source. If it looks like it holds a credential, that function is **not sent at
all** (it keeps the deterministic docstring) and the run summary says how many
were withheld. It looks for:

- private-key headers, AWS access-key IDs, Google (`AIza...`), `sk-...`, GitHub
  (`ghp_`, `github_pat_`, ...) and Slack (`xox...`) tokens, JSON Web Tokens;
- URLs with a password in them (`scheme://user:password@host`);
- a string of eight or more characters with no spaces assigned to a name that
  contains `password`, `secret`, `api_key`, `token` or `private_key`.

This is a safety net, not a scanner. It only looks at the source text being
sent (for a function, that includes its docstring and comments). For a class,
your existing attribute descriptions are sent as context but are not part of
the scanned outline. It cannot recognise a secret that has none of the shapes
above, for example personal data written into a comment or an example.
**Check your comments and docstrings before using `--ai-draft` on code that
contains personal, financial or otherwise sensitive data.**

## Consent

- The first time you use a destination you are asked, on stderr, to agree. The
  answer is stored per destination (`hosted`, or the provider name) in
  `~/.pycodecommenter/consent.json`, outside any project.
- The agreement carries a version number. If what is sent or what a destination
  does with it materially changes, the notice is shown again.
- `--yes-send-code-to-ai` records consent without asking, for CI. Use it only
  where sending that code is already permitted.
- For a directory, the tool first says how many requests it would make and asks
  before sending; `--max-drafts N` caps the run. `--dry-run` and `--output-dir`
  still send code (drafting is what sends it); they only leave your files
  untouched.
- Keys are read from the provider's environment variable or typed at a hidden
  prompt. They are never read from or written to a project file.

## Where the code goes

### Hosted service (default)

Requests go over HTTPS to `https://pycodecommenter-backend.onrender.com`
(override with `PYCODECOMMENTER_AI_BACKEND_URL`). The consent notice in v2.6.0
says the service forwards to Google's Gemini API.

- Limit: a daily allowance per caller, reported in response headers.
  [PLACEHOLDER: how a caller is identified (IP address? something else?).]
- Storage: [PLACEHOLDER: what the service stores or logs (request bodies?
  metadata? IP addresses?), for how long, where it is hosted, who can read it.]
- The current consent notice states "No source code is stored beyond the time
  it takes to process each request." [PLACEHOLDER: confirm this is true of the
  service and of any logs, or reword it.]
- Model provider behind it: [PLACEHOLDER: which model provider(s) and under
  which account tier, since a provider's free tier and paid tier treat data
  differently (see below).]
- Who runs it and how it is maintained: [PLACEHOLDER].

### Your own key

Requests go straight from your machine to the vendor's API using its official
SDK; PyCodeCommenter's service is not involved. The vendor's own terms and data
policy for your account apply. The vendors' current published position is
summarised in `phase2-research.md` (dated 2026-09-29) and should be re-checked
before this page is published.

| `--ai-provider` | Goes to |
|---|---|
| `gemini` | Google Gemini API |
| `openai` | OpenAI API |
| `anthropic` | Anthropic API |
| `deepseek` | `https://api.deepseek.com` (DeepSeek states its processing is in the People's Republic of China) |
| `openai-compatible` | the endpoint you give with `--ai-base-url` (for example a local server) |

## What is written back

Drafted text goes into your docstrings, each line marked
`(AI-drafted, unreviewed)` until you accept it in `pycodecommenter review`.
Each drafted value is checked before it is written (no triple quotes,
backslashes or marker text).

## If you cannot send code to a third party

Do not use `--ai-draft`. The rest of the tool works entirely offline, and the
gaps stay as explicit `TODO(pycodecommenter): describe` markers for a person to
fill. `--ai-provider openai-compatible --ai-base-url <local server>` keeps
requests on a machine you control.

## Reporting a problem

[PLACEHOLDER: contact for privacy or security reports; the repository's
issue tracker is public and should not be used for anything sensitive.]
