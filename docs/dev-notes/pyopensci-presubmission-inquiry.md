Submitting Author: Nabasa Amos (@AmosQuety)
Package Name: pycodecommenter
One-Line Description of Package: Deterministic, AST-based generator, validator, and coverage tool for Google-style Python docstrings.
Repository Link (if existing): https://github.com/AmosQuety/PyCodeCommenter
EiC: TBD

---

## Code of Conduct & Commitment to Maintain Package

- [ ] I agree to abide by [pyOpenSci's Code of Conduct][PyOpenSciCodeOfConduct] during the review process and in maintaining my package after should it be accepted.
- [ ] I have read and will commit to package maintenance after the review as per the [pyOpenSci Policies Guidelines][Commitment].

## Description

- Include a brief paragraph describing what your package does:

PyCodeCommenter helps Python projects keep their documentation accurate as the code changes. It does three things: (1) **generate**: it reads a function's real signature with the standard-library `ast` module and fills in missing parts of a Google-style docstring, including parameters, return values, and the exceptions the function raises. It merges into existing docstrings and never overwrites text the author wrote. (2) **validate**: it checks existing docstrings against the actual code and reports "documentation drift", such as undocumented or orphaned parameters, missing `Returns:`/`Raises:` sections, type mismatches, and placeholder text. It exits non-zero on errors, so it can block a CI run. (3) **coverage**: it measures how much of a project has docstrings, with JSON output and a badge. By default the package is deterministic and makes no network calls. It requires Python 3.10 or newer (CI runs 3.10-3.13) and handles modern syntax (PEP 604/585 types, `async def`, positional- and keyword-only parameters). It runs from a CLI or a Python API.

## Associated Publication (Optional)

Publication Title:

Publication DOI:

Journal/Venue:

## Community Partnerships

- [ ] Astropy: [My package adheres to Astropy community standards](https://www.pyopensci.org/software-peer-review/partners/astropy.html)
- [ ] Pangeo: My package adheres to the [Pangeo standards listed in the pyOpenSci peer review guidebook][PangeoCollaboration]

## Scope

- Please indicate which [category or categories][PackageCategories] this package falls under:

    - [ ] Data retrieval
    - [ ] Data extraction
    - [ ] Data processing/munging
    - [ ] Data deposition
    - [x] Data validation and testing
    - [ ] Data visualization
    - [x] Workflow automation
    - [ ] Citation management and bibliometrics
    - [ ] Scientific software wrappers
    - [ ] Database interoperability

## Domain Specific

- [ ] Geospatial
- [ ] Education

---

- Explain how and why the package falls under these categories (briefly, 1-2 sentences). For community partnerships, check also their specific guidelines as documented in the links above. Please note any areas you are unsure of:

PyCodeCommenter is a tool for developing research software rather than for handling research data, so no category fits exactly. **Workflow automation**: it generates missing docstrings and enforces documentation standards in CI and pre-commit, exiting non-zero on errors. **Data validation and testing**: the object being validated is code documentation (docstrings checked against real signatures), not research data. I'm unsure whether developer tooling of this kind is in scope, and I'd like the editors' view.

- Who is the target audience and what are the scientific applications of this package?

The audience is scientists and research software engineers who maintain Python packages, especially small teams without dedicated documentation reviewers. Accurate API documentation affects reproducibility and reuse: a docstring that describes old parameters or return values leads users to call scientific functions incorrectly. PyCodeCommenter catches that drift automatically. It also fills in documentation scaffolding that tools like Sphinx/MkDocs then render. It does not do any scientific computation itself.

- Are there other Python packages that accomplish similar things? If so, how does yours differ?

- **interrogate / docstr-coverage** measure whether docstrings exist. PyCodeCommenter measures coverage too, but it also checks whether the docstrings are *correct* and can generate the missing ones.
- **pydoclint, darglint (archived), and Ruff's pydocstyle (`D`) rules** check docstrings against signatures or style conventions. PyCodeCommenter's validator overlaps with them, and in addition it generates docstrings and merges them into existing ones without discarding text the author wrote.
- **pyment / docformatter** convert or reformat docstrings. PyCodeCommenter generates content from the AST, including exception conditions and simple boolean return expressions read directly from the code, and marks anything it can't state exactly with a TODO instead of guessing.
- **LLM-based docstring tools** produce fluent text but can describe behaviour that isn't in the code. PyCodeCommenter is deterministic by default, so the same input always produces the same output.

- Any other questions or issues we should be aware of:

One opt-in feature, `generate --ai-draft`, sends function source code to an AI service to draft the descriptions the code can't state. It is off by default. It sends nothing until the user consents (recorded once per destination, and re-asked if the notice changes; `--yes-send-code-to-ai` skips the prompt for CI). The destination is either a hosted backend run by the maintainer or, using the user's own key, a provider such as Gemini, OpenAI, Anthropic or DeepSeek (their SDKs are optional extras, and keys are never stored in a project file). Writing AI drafts in place needs the separate `--accept-ai-drafts` flag. Every drafted line is marked "(AI-drafted, unreviewed)", and the validator reports those lines under their own category. Note that `coverage` measures docstring presence only, so it counts AI-drafted docstrings as documented. Without the flag, the package makes no network calls. I'm happy to discuss whether reviewers would prefer this feature separated out.
