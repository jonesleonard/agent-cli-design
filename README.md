# Agent CLI Design

An agent-ready CLI design skill for Claude Code and other coding agents.
It covers non-interactive behavior, structured output, exit codes, safe
mutations, errors, security, discoverability, and audits of existing CLIs.

## Install

From GitHub:

```bash
npx skills add <owner>/agent-cli-design
```

From this local checkout during development:

```bash
npx skills add . --agent claude-code
```

Local installs use a symlink by default, so edits to this checkout are
available to the installed skill. Use `--copy` when a standalone copy is
preferred.

## Development

- `SKILL.md` contains the skill instructions.
- `references/` contains detailed guidance loaded when needed.
- `scripts/probe_cli.py` provides a safe CLI audit probe.
- `evals/` contains evaluation prompts and their small test fixtures.

Generated evaluation runs are kept in the ignored
`agent-cli-design-workspace/` directory.
