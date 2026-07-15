You have a full engineering audit attached @More future work.md. This is a
multi-phase task with HARD STOPS between phases. You are not permitted to
combine phases, skip ahead, or make architecture decisions on my behalf,
even if the next step seems obvious.

GLOBAL RULES (apply to every phase):
- Work on a new git branch (e.g. `fix/audit-phaseN`). Do not commit to main.
- Each phase lists the EXACT files you are allowed to modify. Do not touch
  any other file. If you believe another file must change to complete the
  phase, STOP and tell me why instead of doing it.
- At the end of each phase, paste the FULL, UNTRUNCATED output of:
    git diff --stat
    git diff
    python -m pytest -v
  Do not summarize test results in prose ("37 passed") instead of pasting
  the actual output. I want to see the real terminal output.
- After posting the above, write exactly: "PHASE N COMPLETE — WAITING FOR
  APPROVAL" and STOP. Do not start the next phase in the same response,
  even partially. Do not pre-write code for the next phase "for
  efficiency."
- If completing a phase requires a design decision not specified below
  (e.g. which library to use, which of two valid approaches to take),
  STOP and ask me. Do not pick one yourself and proceed. A bracketed note
  like "[we'll decide together]" means you must ask a direct question and
  wait — it is not permission to choose.

---

PHASE 1 — Trivial fixes (files: commenter.py, validator.py, type_analyzer.py)
- Fix PyCodeCommenter.validate() to pass self.file_path instead of None
- Fix check_coverage() to use the real file path instead of "<string>"
- Rename `infos` -> `info` consistently (backward-compatible alias is fine)
- Fix PEP 604 rendering: `X | Y` instead of `Union[X, Y]`
Do NOT touch get_patched_code() in this phase.

---

PHASE 2 — Regression tests ONLY (files: test_edge_cases.py, and any new
test file you create — NO source files under PyCodeCommenter/ may change)
- Write a test that reproduces the multi-line signature corruption bug
  (Question 2, first CRITICAL issue in the audit)
- Write a test that reproduces the line-shift insertion bug
- Run the tests and paste output PROVING they fail against the current
  (unfixed) source code. A test that passes at the end of this phase is a
  FAILURE of this phase — it means either the test is wrong or you fixed
  the bug early, both of which are not allowed here.
- Do not modify commenter.py, validator.py, or type_analyzer.py in this
  phase under any circumstance.

---

PHASE 3 — Fix the patcher (BLOCKED until I respond to a question)
Before writing any code in this phase, ask me directly: "Should I use
libcst, or the ast.unparse() fallback?" and list, in your own words, the
tradeoffs of each — specifically including: does this approach preserve
comments in the source file? Does it preserve formatting/quote style?
What new dependency (if any) does it add?
Wait for my answer before writing any implementation code.
Once I've answered:
- Implement the chosen approach in get_patched_code() only
- Make the Phase 2 tests pass
- Add a NEW test that checks whether comments in the source file survive
  patching, and tell me honestly whether they do or don't
- Confirm no other existing tests regress

---

PHASE 4 (files: cli.py, config.py)
- Add directory support to `validate` and `generate` CLI commands
- Add --fail-below to coverage CLI
- Wire load_config() into cli.py

---

PHASE 5 (files: validator.py, docstring_parser.py)
- Fix ast.walk() double-counting nested functions
- Fix hardcoded 8-space continuation-line parsing

---

Begin with Phase 1 only. Stop after Phase 1 and wait for my explicit
approval before starting Phase 2.