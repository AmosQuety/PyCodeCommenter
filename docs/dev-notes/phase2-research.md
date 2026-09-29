# pyOpenSci prep: Phase 2 research (2026-09-29)

Research only. Nothing in the package, README or docs was changed because of
it. Pages were read with a fetch tool that summarises them, so quotes should
be re-checked against the linked page before anything is published. Two
OpenAI terms pages returned HTTP 403 and were not read.

## B3. Default model IDs

| Provider | Default in code/README | Real today? | Notes | Source |
|---|---|---|---|---|
| OpenAI | `gpt-6-astra` | Yes, listed | It is the **flagship** ($10 in / $50 out per million tokens). The same page lists `gpt-6-sol` ($2/$10) and `gpt-6-luna` ($0.1/$0.5, "most efficient ... high-volume tasks"). For one-sentence docstrings the default is the most expensive option | https://developers.openai.com/api/docs/models |
| DeepSeek | `deepseek-flash` | Yes | Current name for DeepSeek-V4.1-Flash. Legacy names such as `deepseek-v4-flash` are still accepted. Base URL `https://api.deepseek.com` matches the code | https://api-docs.deepseek.com/quick_start/pricing |
| Anthropic | `claude-haiku-4-5-20251001` | Yes, Active | **Retirement "not sooner than October 15, 2026"**, about two weeks away, and at least 60 days' notice is promised before retirement. Current lineup is `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`; the README example `claude-opus-5` is Legacy but Active (not sooner than July 24, 2027) | https://platform.claude.com/docs/en/about-claude/models/overview and https://platform.claude.com/docs/en/about-claude/model-deprecations |
| Gemini | `gemini-2.5-flash` | Exists, no shutdown date | Google says it is "limiting access to the 2.5 models to users who have actively used them in the past" and recommends 3.5 Flash-Lite or 3.8 Flash for new projects. A new user with a new key may be refused, which is the "model not found"-style failure the plan warned about | https://ai.google.dev/gemini-api/docs/models and https://ai.google.dev/gemini-api/docs/deprecations |

Decisions for you (nothing changed): the IDs all exist, but two defaults are
risky. Gemini 2.5 may be closed to new users. Haiku 4.5 has a retirement
date that could arrive within the review window. The comment in
`direct_providers.py` says `gemini-3.8-flash` was overloaded during testing in
2026-09, which is why 2.5 was chosen. OpenAI's default is the priciest model.
Also `direct_providers.py` `_EFFORT_MODELS`/`_FALLBACK_MODELS` use the prefix
`claude-opus-5`, which still matches `claude-opus-5-5`.

## A4. What each provider's terms say about sending user code

Not legal advice; these are the parts relevant to a tool that sends the user's
own source through the user's own key.

- **Google Gemini API.** Terms: https://ai.google.dev/gemini-api/terms . On
  the unpaid tier Google "uses the content you submit ... to provide, improve,
  and develop Google products"; on the paid tier it "doesn't use your prompts
  ... or responses to improve our products" and logs them for a limited time
  for safety and legal reasons (stricter rules for the EEA/UK/Switzerland even
  when unpaid). No use of the service to build competing models. Consequence:
  a free-tier key means the user's code may be used for product improvement.
- **OpenAI API.** Data controls: https://developers.openai.com/api/docs/guides/your-data .
  API data is not used to train models unless the customer opts in; abuse
  monitoring logs are kept up to 30 days; eligible customers can get zero data
  retention. The services agreement (https://openai.com/policies/services-agreement/)
  and business terms (https://openai.com/policies/business-terms/) returned
  403, so what they say about the customer's right to submit content and
  usage restrictions is **not read**.
- **Anthropic API.** Commercial terms: https://www.anthropic.com/legal/commercial-terms .
  "Anthropic may not train models on Customer Content from Services"; the
  customer represents it "has all rights and permissions required to submit
  Inputs"; no building a competing product or training competing models.
  Retention: inputs and outputs deleted within 30 days by default, with
  exceptions (https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data).
- **DeepSeek.** Terms: https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html
  and privacy policy: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html .
  The user is responsible for inputs and warrants the right to submit them. The
  privacy policy says data is processed and stored "in People's Republic of
  China", gives users a right to opt out of training use of personal data
  (implying training use by default), and has no specific retention period.
  Relevant if the code or its comments hold citizen or financial data.
- **Common thread.** In every case the user, not PyCodeCommenter, is the
  customer and must have the right to send that code. None of the pages read
  forbids sending source code for documentation. That is my reading of
  summaries, not confirmed against the full legal text, and I did not read
  the hosted backend's upstream terms (see the draft page's placeholders).

Whether the "does not violate the Terms of Service of any service it interacts
with" box can be ticked is your call; I have not ticked or claimed anything.
The parts I could not check: OpenAI's agreements (403), the hosted service's
own terms and upstream provider, and the terms of any OpenAI-compatible
endpoint a user chooses.

The draft page is `data-and-privacy-draft.md` in this folder.

## A6. Does main match the 2.6.0 release on PyPI?

Yes for the package code.

- `origin/main` = tag `v2.6.0` = commit `85a535b` ("Fix/2.6.0 test phase
  findings (#7)", 2026-09-27 02:08 +03:00, i.e. 2026-09-26 23:08 UTC).
- PyPI 2.6.0 wheel and sdist uploaded 2026-09-26 23:51 UTC; the GitHub release
  was published 23:50 UTC. The "Sept 26 vs Sept 27" mismatch in the plan is
  the +03:00 timezone: the tag is about 40 minutes older than the upload.
- `diff -r` of the wheel's `PyCodeCommenter/` against `origin/main` shows no
  differences. Wheel metadata version is 2.6.0 with the same dependencies.
- Not compared: the sdist contents, and non-package files. They are not in the
  wheel.
- `CITATION.cff` says `date-released: 2026-09-24`, and `CHANGELOG.md` says
  `2026-09-27`; the release went out on 2026-09-26 UTC. These need aligning
  with whatever release you submit.
- Correction to my Phase 1 report: I said the branch sat 37 commits ahead of
  `main`. That compared against a stale **local** `main` (118e904). The
  `fix/2.6.0-test-phase-findings` tree is identical to `origin/main` (it was
  squash-merged as #7), and `pyopensci-prep` branches from it. The branch
  holds 80 commits by `origin/main..` because of the squash; the tree diff
  against `origin/main` is just my Phase 1 work.
