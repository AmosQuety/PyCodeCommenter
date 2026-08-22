# Project Skills

Skills placed here (`.claude/skills/<skill-name>/SKILL.md`) are specific to
**this repository** — PyCodeCommenter. They're checked into git, so anyone
who clones the repo and runs Claude Code here gets them automatically.

## What belongs here

Anything that encodes knowledge about *this codebase's* workflows — things a
new contributor to this specific project would need to be told, e.g.:

- How to regenerate `docs/` and validate the MkDocs build.
- How to bump the version consistently across `pyproject.toml` and
  `PyCodeCommenter/__init__.py` (see the "Versioning" note in `../../CLAUDE.md`).
- A checklist for adding a new validation check to `validator.py` (update the
  check, the docs, and the relevant `test_validation.py` cases together).

## How this differs from `~/.claude/skills/`

| | `~/.claude/skills/` (global) | `.claude/skills/` (this file's location) |
|---|---|---|
| Scope | Every project on this machine | Only this repository |
| Checked into git | No — lives in your home directory | Yes — shared with collaborators |
| Good for | Personal workflows (e.g. your own commit-message style) | Repo-specific workflows (e.g. this project's release process) |

Each skill is a subdirectory containing a `SKILL.md` with YAML frontmatter
(`name`, `description`) plus body instructions — see
`~/.claude/skills/commit-helper/SKILL.md` for a working example of the format.

This directory is currently empty.
