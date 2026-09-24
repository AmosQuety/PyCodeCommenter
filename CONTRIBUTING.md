# Contributing to PyCodeCommenter

Thanks for considering a contribution. Bug reports, ideas, documentation
fixes and code are all welcome. Everyone taking part is expected to follow
the [Code of Conduct](https://github.com/AmosQuety/PyCodeCommenter/blob/main/CODE_OF_CONDUCT.md).

## Reporting bugs

1. Check the [issues](https://github.com/AmosQuety/PyCodeCommenter/issues)
   to see whether it's already been reported.
2. If not, open an issue with a short title, what you expected, what happened
   instead, and the smallest piece of Python code that shows it. Include the
   output of `pycodecommenter --version` and your Python version.

## Proposing a change

Open an issue first for anything bigger than a small fix, so we can agree on
the approach before you spend time on it.

## Setting up for development

You need Python 3.10 or newer.

```bash
git clone https://github.com/AmosQuety/PyCodeCommenter.git
cd PyCodeCommenter
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                 # format and lint on every commit
```

To work on the bring-your-own-key AI providers, also install their SDKs:
`pip install -e ".[dev,ai]"`. The tests don't need them.

## Running the checks

```bash
pytest            # the test suite (tests/) and the package's doctests
black .           # formatting
flake8            # linting
```

The tests never make network calls: AI providers are tested against fake
clients. Continuous integration runs the suite on Python 3.10–3.13 for every
pull request.

If you change how docstrings are generated, also compare the output before
and after your change on a few real files:

```bash
git archive main | tar -x -C /tmp/before
python scripts/compare_generation.py /tmp/before . path/to/some/python/files
```

"broken output" and "code changed" must stay at 0.

## Pull requests

1. Fork the repository and branch from `main`.
2. Write a test that fails without your change, then make it pass.
3. Keep the change focused; update `README.md`, `docs/` and the
   `[Unreleased]` section of `CHANGELOG.md` if users will notice it.
4. Make sure `pytest`, `black --check .` and `flake8` pass.
5. Open the pull request with a clear description of what changed and why.

## Code style

- [Black](https://github.com/psf/black) formatting, [flake8](https://flake8.pycqa.org/) linting.
- Google-style docstrings (the style the tool itself writes).
- Python 3.10+ syntax is fine.
- The generator only states what the code proves; anything else stays a
  `TODO` marker or, with `--ai-draft`, a labelled draft. Please keep it that
  way: see `docs/dev-notes/docstring-prose-quality.md` for why.

Maintainers: the current state of work and the decisions behind it are in
[`docs/dev-notes/`](https://github.com/AmosQuety/PyCodeCommenter/blob/main/docs/dev-notes/README.md).

## Questions

Open an issue — there are no silly questions.
