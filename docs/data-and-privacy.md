---
title: Data and Privacy — PyCodeCommenter
description: What PyCodeCommenter sends when you use AI drafting, what is filtered out first, where it goes, and how consent works.
keywords: pycodecommenter privacy, ai drafting data, docstring generator privacy, source code sent to ai
---

# Data and Privacy

PyCodeCommenter sends nothing anywhere unless you ask it to draft with AI. This page says exactly what is sent when you do, where it goes, and how to avoid it.

## The short version

- `generate` without `--ai-draft`, `validate`, `coverage` and `review` make **no network calls**.
- With `--ai-draft`, the source of the functions and classes that have gaps is sent to **one service that you choose**, after you agree once for that destination.
- You choose between PyCodeCommenter's **hosted service** and **your own key** with a vendor (Gemini, OpenAI, Anthropic, DeepSeek, or any OpenAI-compatible endpoint). Your key is never sent to the hosted service.
- If you cannot send your code to a third party, do not use `--ai-draft`. The rest of the tool works entirely offline.

## What is sent

For each function that has a gap, one request carries:

| Item | Detail |
|---|---|
| The function's name | |
| Its parameters | name, inferred type, default value as written |
| Return type, whether it is a generator, exceptions it raises | read from the code |
| **The function's source** | from the `def` line to its last statement, **including its docstring and any comments inside the body**. Decorators and comments above the `def` are not included |
| Text already settled | your existing parameter, return and exception descriptions, so a draft stays consistent with them |
| Which parts are wanted | for example the summary, parameter `x`, the return value |

For each class that has a gap: its name and base classes, its attributes with their types, an **outline** (the class line, class-level statements, `__init__` in full, and every other method as its signature only), and your existing attribute text.

**Not sent:** functions and classes with nothing to draft, the rest of the file, other files, module docstrings, and your file names and paths. Your API key goes only to the vendor it belongs to.

## What is filtered out first

Before a function or class is sent, its source is checked. If it looks like it holds a credential, that function is **not sent at all** (it keeps the deterministic docstring), and the run summary says how many were withheld. The check looks for:

- private-key headers, AWS access-key IDs, Google (`AIza...`), `sk-...`, GitHub (`ghp_`, `github_pat_`, ...) and Slack (`xox...`) tokens, and JSON Web Tokens;
- URLs with a password in them (`scheme://user:password@host`);
- a string of eight or more characters with no spaces assigned to a name containing `password`, `secret`, `api_key`, `token` or `private_key`.

This is a safety net, not a scanner. It only looks at the source text being sent (for a function, that includes its docstring and comments). For a class, your existing attribute descriptions are sent as context but are not part of the scanned outline. It cannot recognise sensitive data that has none of the shapes above, for example personal data written into a comment or an example.

!!! warning
    Check your comments and docstrings before using `--ai-draft` on code that contains personal, financial or otherwise sensitive data.

## Consent

- The first time you use a destination you are asked, once, to agree. The answer is stored per destination (`hosted`, or the provider's name) in `~/.pycodecommenter/consent.json`, outside any project.
- The agreement carries a version number. If what is sent, or what a destination does with it, materially changes, the notice is shown again.
- `--yes-send-code-to-ai` records consent without asking, for CI. Use it only where sending that code is already permitted.
- For a directory, the tool first says how many requests it would make and asks before sending. `--max-drafts N` caps the run.
- `--dry-run` and `--output-dir` still send code, because drafting is what sends it. They only leave your files untouched. Writing with `--inplace` also requires `--accept-ai-drafts`.
- Keys are read from the provider's environment variable or typed at a hidden prompt. They are never read from or written to a project file.

## Where the code goes

### The hosted service (default)

Requests go over HTTPS to `https://pycodecommenter-backend.onrender.com` (you can point them elsewhere with the `PYCODECOMMENTER_AI_BACKEND_URL` environment variable). The service is a separate open-source project, [PyCodeCommenter-Backend](https://github.com/AmosQuety/PyCodeCommenter-Backend), run by the maintainer of PyCodeCommenter.

- **What it does with your code.** It forwards the request to Google's Gemini API using the maintainer's API keys and returns the draft. The service does not store your code: it has no database and keeps no copy of requests.
- **What it logs.** For each draft it logs only the function or class name, the outcome (success, decline or failed), the time taken, and a count of proxy hops. The service's own code does not log your source, the drafted text or your IP address. The hosting platform, Render's free plan, keeps its own logs, and only temporarily.
- **Google.** The maintainer's Gemini keys are on Google's **free tier**. Under [Google's Gemini API terms](https://ai.google.dev/gemini-api/terms), content sent on the free tier may be used to improve Google's products. So code sent through the hosted service is handled by Google under those terms. **If that is not acceptable for your code, use your own key or do not use `--ai-draft`.**
- **Who is a caller.** Callers are told apart only by the IP address of the request; there is no account or login. Each caller gets a daily allowance (25 drafts in v2.6.0, counted per UTC day), plus a per-minute limit and a shared daily cap. The counters are held in memory, so they also reset when the service restarts.
- **No authentication.** Anyone can call the service directly. The limits bound nuisance, not misuse, so do not treat the service as a place for anything sensitive.
- **Cold starts.** It runs on a free plan that sleeps when idle, so the first request after a pause can take tens of seconds.
- **If it is switched off,** the tool offers to continue with your own key.

### Your own key

Requests go straight from your machine to the vendor's API using its official SDK. PyCodeCommenter's service is not involved, and the vendor's own terms and data policy for your account apply. Read them before sending code you do not own:

| `--ai-provider` | Goes to | Terms and data policy |
|---|---|---|
| `gemini` | Google Gemini API | [Gemini API terms](https://ai.google.dev/gemini-api/terms) |
| `openai` | OpenAI API | [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data) |
| `anthropic` | Anthropic API | [Anthropic commercial terms](https://www.anthropic.com/legal/commercial-terms) |
| `deepseek` | `https://api.deepseek.com` | [DeepSeek terms](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) and [privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html) |
| `openai-compatible` | the endpoint you give with `--ai-base-url` (for example a local server) | the endpoint operator's |

These policies change and differ between free and paid tiers, so check the current version. Two things worth knowing before you choose: the free tier of some vendors allows use of your content to improve their products, and DeepSeek's privacy policy states that its processing and storage are in the People's Republic of China.

To keep every request on a machine you control, use `--ai-provider openai-compatible --ai-base-url <address of a local server>`.

## What is written back

Drafted text goes into your docstrings, each line marked `(AI-drafted, unreviewed)` until you accept it in `pycodecommenter review`. Every drafted value is checked before it is written: no triple quotes, backslashes or marker text.

## Reporting a problem

Send privacy or security reports to **amosnabasa4@gmail.com**. The repository's issue tracker is public, so do not put anything sensitive in an issue.
