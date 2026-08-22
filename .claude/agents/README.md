# Project Subagents

Subagent definitions placed here (`.claude/agents/<agent-name>.md`) are
specific to **this repository** — PyCodeCommenter. They're checked into git,
so anyone using Claude Code on this repo gets the same specialized agents.

## What belongs here

A subagent is a focused persona with its own system prompt and (optionally)
a restricted tool set, invoked for a particular kind of task. For this repo,
that might look like:

- A "validator-check-reviewer" agent that knows the six validation rules in
  `PyCodeCommenter/validator.py` and reviews changes to them for correctness
  and test coverage.
- A "docstring-style-checker" agent that enforces the Google-style docstring
  conventions this project itself generates and validates.

Each file is Markdown with YAML frontmatter defining the agent's name,
description (used to decide when it's invoked), and optionally which tools
it can access — e.g.:

```markdown
---
name: example-agent
description: One-line description of when to use this agent.
tools: Read, Grep, Glob
---

System prompt / instructions for the agent go here.
```

## How this differs from user- or account-level agents

| | Project agents (this directory) | Global/personal agents |
|---|---|---|
| Scope | Only this repository | Every project you work on |
| Checked into git | Yes — shared with collaborators | No — lives outside the repo |
| Good for | Tasks tied to this codebase's specific modules/conventions | General-purpose personas you reuse everywhere |

This directory is currently empty.
