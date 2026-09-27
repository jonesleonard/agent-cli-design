# Discoverability, naming, and stability

## Contents

- [How agents learn a CLI](#how-agents-learn-a-cli)
- [Help text](#help-text)
- [Command grammar](#command-grammar)
- [Naming policy](#naming-policy)
- [Stability contract](#stability-contract)
- [Shipping guidance: AGENTS.md snippets and skills](#shipping-guidance-agentsmd-snippets-and-skills)
- [CLI vs MCP](#cli-vs-mcp)

## How agents learn a CLI

In practice an agent: runs `tool --help`, picks a subcommand, runs
`tool <cmd> --help`, copies an example, adjusts it, runs it, and reads the
error if it fails. It relies heavily on patterns from other CLIs it has seen.
So the most effective documentation is: good help text, conventional names,
and errors that correct it. Long external docs are rarely read mid-task.

Progressive disclosure matters: top-level help should be a short menu, not a
manual. Detail lives one level down.

## Help text

Template for a subcommand:

```text
Deploy a service to an environment.

Usage:
  tool deploy <service> --env <env> [flags]

Arguments:
  service            Service name (required)

Flags:
  --env string       Target environment: dev, staging, prod (required)
  --image string     Image override (default: from tool.toml)
  --wait             Block until rollout completes (default: true)
  --timeout dur      Max time to wait (default: 5m)
  --dry-run          Show planned changes without applying
  --json             Output JSON

Examples:
  tool deploy web --env staging
  tool deploy web --env prod --image registry.io/web:v2.1.0 --json
  tool deploy web --env prod --dry-run

Exit codes: 0 ok, 2 usage, 3 not found, 4 auth, 6 transient (see: tool help exit-codes)
```

Checklist:

- One-line description first.
- A usage line that is itself a contract: required things in `<>`, optional in
  `[]`.
- Required vs optional is explicit; defaults and valid values are stated.
- 2–4 realistic examples using plausible values, not `foo`/`bar`. Include the
  JSON and dry-run forms.
- Mention stdin support explicitly (`-f -` reads from stdin).
- `--help` and `-h` work everywhere, print to stdout, exit 0, and never
  require auth or network.
- A `help <topic>` or docs command for cross-cutting topics (exit codes,
  config, auth) keeps per-command help short.

## Command grammar

Use a noun-verb hierarchy for multi-resource CLIs:

```text
tool user list
tool user get <id>
tool user create --email ...
tool user group add <user> <group>
```

`tool --help` then reads as a list of resources and `tool user --help` as a
list of actions — a tree the agent can search deterministically. Small
single-purpose tools (`jq`, `rg`) don't need this; don't impose it on them.

Keep argument style consistent: identifiers as positional arguments,
everything else as named flags. Avoid multiple positionals whose order is easy
to confuse; use flags instead (`--from`, `--to`).

## Naming policy

Write the policy down and enforce it with a test that walks the command tree.

Verbs: `list`, `get`, `create`, `update`, `delete`, plus `apply`/`ensure` for
declarative ops. Avoid `ls`, `info`, `show`, `rm`, `remove` as primary names.
Aliases are fine for humans, but help text and examples should use the
canonical name.

Global flags:

| Concept | Flag |
| --- | --- |
| JSON output | `--json` (or `--output json`, but only one of them) |
| Skip confirmation | `--yes`, `-y` |
| Override safety check | `--force`, `-f` |
| Preview | `--dry-run` |
| Non-interactive | `--no-input` |
| Page size / continuation | `--limit`, `--cursor` |
| Field selection | `--fields` |
| Bare output | `--quiet`, `-q` |
| Verbosity | `--verbose`, `-v` |
| Color | `--no-color`, and honor `NO_COLOR` |
| Time bound | `--timeout` |
| Version | `--version` |

When you must invent a concept, name it once and reuse it everywhere.

## Stability contract

Once agents depend on a CLI, command names, flag names and meanings, JSON
field names and types, and exit codes are an API. Agents learn shapes from
earlier runs, copied prompts, skills, and eventually training data; a rename
breaks them in ways that look like hallucination.

- Change additively: new commands, new flags, new fields.
- Deprecate with a stderr warning naming the replacement; keep the old path
  working for a long time.
- Snapshot-test `--help` output, JSON shapes (or a JSON Schema), and exit codes
  so accidental changes fail CI.
- `tool --version` prints a parseable version; `tool --version --json` is a
  nice extra that can include API/schema versions.

## Shipping guidance: AGENTS.md snippets and skills

Two complementary ways to teach agents a CLI:

- **An `AGENTS.md`/`CLAUDE.md` snippet** that users paste into their project.
  It's always in context, so it's reliably read. Keep it short: what the tool
  is for, the flags to always use (`--json`, `--no-input`), the confirmation
  policy, and pointers to `tool <cmd> --help`. Vercel's evals found a compact
  docs index in `AGENTS.md` outperformed an equivalent skill because agents
  often didn't invoke the skill.
- **A skill** (Agent Skills format, `SKILL.md`) for multi-step workflows
  ("publish a release end to end", "diagnose a failed deploy"). Several small,
  focused skills with sharp trigger descriptions work better than one giant
  skill.

A CLI can also point to these itself (`tool agents-md` prints the snippet;
`tool skills` prints the install command) so an agent that only has the binary
can find them. Keep generated guidance in sync with the command surface — stale
docs that describe removed flags are worse than none.

## CLI vs MCP

They're peers, not rivals. Share one domain model underneath both.

- **CLI** fits when the agent has a shell, the workflow composes with other
  tools, it needs to run in CI, or context cost matters (a CLI costs nothing
  until it's called; its help is loaded on demand).
- **MCP** fits when the client has no shell, the host should manage auth and
  approval UI, or you need typed tool schemas without a local binary.
- Very large API surfaces don't fit well as one-tool-per-endpoint MCP. A
  search-and-execute design (e.g. Cloudflare's Code Mode: ~2,500 endpoints
  behind two tools in roughly 1,000 tokens) or a CLI with good progressive
  help scales better.
