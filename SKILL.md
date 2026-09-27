---
name: agent-cli-design
description: 'Use this skill whenever a user designs, builds, changes, audits, or troubleshoots a command-line interface for automation: AI agents, Claude Code, Codex, Cursor, CI, scripts, or headless use. Consult it even when they only mention a CLI command tree, flags, --json output, stdout/stderr, exit codes, prompts that hang, confirmation or destructive actions, retries or idempotency, pagination, token authentication, async jobs, CLI-vs-MCP choices, or inconsistent help text. It provides a language-agnostic workflow for new CLIs, retrofits, and evidence-based audits covering non-interactive behavior, structured output, safe mutations, errors, security, discoverability, and optional async/profile patterns. Do not use it for a simple one-off CLI command, general CLI explanations, installation docs, ordinary code refactors, or an MCP-only integration with no shell interface.'
license: MIT
---

# Agent-Ready CLI Design

A CLI that agents call is an API whose transport is a shell. The caller is
fast, literal, and tireless, but it cannot see a prompt, cannot eyeball a
table, will retry on failure, and will replay whatever command shapes it saw
last week. Every ambiguity turns into extra turns, wasted tokens, or a wrong
action taken with confidence.

The good news: nearly everything that helps agents also helps scripts, CI, and
humans. Treat this as good CLI design with the tolerance for sloppiness
removed, not as a separate "agent mode" bolted on.

## Pick the workflow

Figure out which situation you are in, then follow that section.

- **New CLI** — the user is designing or scaffolding a tool. Produce a design
  spec before (or alongside) code. See [New CLI](#new-cli).
- **Retrofit** — an existing CLI works for humans but agents struggle. Find
  gaps, then fix in priority order. See [Retrofit](#retrofit).
- **Audit** — the user wants an assessment or scorecard. See [Audit](#audit).
- **Focused question** — e.g. "how should delete work?", "what exit codes?".
  Answer directly using the principles and the relevant reference file; don't
  force a full workflow.

### Shape of the deliverable

- **Size it to the request.** Long documents bury the decisions the reader
  actually needs, and this domain tempts you to include everything you know.
  Rough targets: a focused question ("how should delete work?") gets about
  100–150 lines — lead with the recommendation, show the key invocations and
  outputs, and stop. A full CLI spec rarely needs more than 500 lines. Put
  tempting extras (rollout plans, `AGENTS.md` snippets, harness permission
  rules) in a short "also consider" list of one-liners unless the user asked
  for them.
- **Make it stand alone.** The reader has never seen this skill. Don't refer
  to it, its reference files, or `scripts/probe_cli.py` in user-facing
  documents; describe the check itself or recommend a public tool like
  `cli-agent-lint`.
- **Run a consistency pass before finishing.** Designs in this area fail most
  often by contradicting themselves. Check that every exit code used in an
  example appears in the exit code table with the same meaning, every flag in
  an example is defined, statements about what goes to stdout/stderr match
  every example, and JSON field names are identical wherever they appear.

## Principles

Tiers reflect cost of getting it wrong. **Must** items cause hangs, silent
failures, or damage. **Should** items cause friction: retries, token waste,
guessing. **Consider** items compound value for heavy agent use but are
situational.

### Must

1. **Never block on input.** Every value a prompt could collect must also be
   passable by flag, env var, file, or stdin. When stdin is not a TTY, never
   prompt: use the flag, a documented default, or fail fast with an error
   naming the missing flag. A hung process is the worst possible outcome — the
   agent can't tell it apart from slow work.
2. **Structured output on stdout, everything else on stderr.** Offer JSON for
   every command that returns data. Progress, spinners, warnings, and log lines
   go to stderr. No ANSI color when output isn't a terminal or `NO_COLOR` is
   set. Mutations return the identifiers and URLs the next step needs.
3. **Exit codes carry meaning.** 0 only on success. Non-zero on every failure,
   including partial failure. Use 2 for usage errors (the argparse/Click/POSIX
   builtin convention) and document the rest. See
   `references/output-and-errors.md` for a recommended table.
4. **Errors teach.** Validate inputs locally before side effects or network
   calls. An error names what was wrong, echoes the bad value, lists the valid
   values when the domain is enumerable, and shows a corrected invocation. In
   JSON mode emit a structured error with a stable string `code`.
5. **Mutations are safe to retry and hard to fire by accident.** Make creates
   idempotent (explicit idempotency key, natural key, or `ensure`/`apply`
   semantics) or make conflicts detectable with a distinct code. Offer
   `--dry-run` on anything consequential, with structured output.
   Destructive actions need an explicit, non-default opt-in — see
   `references/safety-and-mutation.md` for choosing between a bypass flag and a
   confirmation protocol. Where the backend allows it, make destruction
   recoverable too: deletion protection on important resources, soft delete
   with a grace period, or a final backup. And be honest about the limit: an
   agent can pass any flag and type any name, so flags and confirmations stop
   accidents, not a determined caller. Stopping an agent from doing something
   takes scoped credentials and server-side policy.

### Should

1. **Help text is the primary documentation.** `tool --help` lists
   subcommands; `tool <cmd> --help` shows a usage line, required vs optional
   flags, defaults, valid values, and 2–4 realistic, copy-pasteable examples.
   Agents adapt examples more reliably than they interpret prose.
2. **Predictable grammar and vocabulary.** Noun-verb hierarchy
   (`tool user create`). Use the community-standard verbs (`list`, `get`,
   `create`, `update`, `delete`) and flags (`--json`, `--yes`, `--dry-run`,
   `--limit`, `--quiet`, `--verbose`, `--version`). One spelling per concept
   across the whole CLI — never `--json` here and `--format json` there.
   Enforce it with a test or lint, not code review.
3. **Bounded output.** Lists default to a page size and say when they're
   truncated and how to narrow or continue (`--limit`, `--cursor`, filters).
   Offer `--fields` to select fields and `--quiet` for bare values one per
   line. Large blobs (logs, files) should be opt-in or written to a path.
4. **The interface is a contract.** Once agents use it, command names, flag
   meanings, JSON field names, and exit codes change additively only. Add new
   things; deprecate loudly; don't rename. Snapshot-test help and JSON shapes.
5. **Headless auth.** A token env var (e.g. `TOOL_TOKEN`) that takes
   precedence over stored credentials. Browser/device flows are for humans.
   Support scoped tokens so an agent can run with less power than its human,
   and never require secrets as flag values (they leak into shell history and
   agent transcripts).
6. **Deterministic and time-bounded.** Stable sort order, ISO 8601 timestamps,
   consistent types for the same field everywhere. A `--timeout` on anything
   that waits on the network; surface rate-limit and retry-after information.
7. **Ship guidance for agents.** A short `AGENTS.md`/`CLAUDE.md` snippet users
   can paste into projects (always in context, so it reliably gets read), plus
   an optional skill for multi-step workflows. See
   `references/discoverability.md`.

### Consider

Async `--wait` with a persistent job ledger, named profiles, a machine-readable
introspection command, output delivery sinks, and a feedback channel. These
pay off for CLIs wrapping long-running or heavily configured APIs, and each
has costs. Read `references/advanced-patterns.md` before recommending any of
them.

Security concerns cut across all tiers — output that carries untrusted text
into the agent's context, secrets in output, hostile inputs. Read
`references/security.md` whenever the CLI touches external data, credentials,
or the filesystem.

## Contested points: use these defaults

Published guidance disagrees on a few things. Use these defaults unless the
user's context argues otherwise, and explain the trade-off when it matters.

| Question | Default | Why |
| --- | --- | --- |
| Skip-prompt flag name | `--yes` (`-y`) skips confirmation; `--force` overrides a safety check (overwrite, delete non-empty, ignore conflict) | Unix convention (`apt -y`, `rm -f`, `git push --force`). Merging them means "don't ask" silently also means "ignore guards". |
| Bypass flag vs confirmation protocol | Bypass flag for local/reversible actions; confirmation envelope (exit code + JSON describing changes + exact `--confirm` command) for production or irreversible changes | The envelope keeps a human in the loop without an interactive prompt and works in CI. |
| JSON by default when not a TTY? | Explicit `--json` must always work. Auto-switching on non-TTY is optional, never the only path | Some agent harnesses allocate a PTY, so TTY detection is unreliable; `tool list \| less` by a human shouldn't surprise them. |
| `--json` vs `--output json` | Either, but exactly one across the CLI. Prefer `--json` for new tools | Short, widely recognized (`gh`, Wrangler). Consistency matters more than the choice. |
| "Did you mean…?" | Listing valid options in an error is good. Auto-running or auto-correcting to a guessed command is not | Enumeration lets the agent self-correct; auto-correction hides that the input was wrong. |
| Exit code numbering | 0 success, 1 general, 2 usage; document the rest and pair with a string error code | No universal standard exists; the numbers are coarse, the string code carries detail. |
| Flat vs nested JSON | Whatever mirrors the domain, with stable names and consistent types | Agents handle nesting fine with `jq`; drift is what breaks them. |

## New CLI

1. **Pin down the surface.** Nouns, verbs, which commands mutate, which are
   destructive or irreversible, which wrap async work, what auth is needed.
2. **Write a design spec** covering:
   - Command tree in noun-verb form, with each command's flags and which are
     required.
   - Global flags (`--json`, `--quiet`, `--yes`, `--dry-run`, `--timeout`,
     `--version`, `--help`) and env vars, with precedence:
     flag > env var > config file > default.
   - JSON output shape for each data-returning command and the error envelope.
   - Exit code table.
   - Mutation policy per command: idempotency strategy, dry-run, and bypass
     flag vs confirmation protocol.
   - Help text for at least one representative command, with examples.
   - Pagination/limit defaults for list commands.
   - The `AGENTS.md` snippet you'd ship.
   Before drafting, read `references/output-and-errors.md`,
   `references/safety-and-mutation.md`, and `references/discoverability.md`.
   Also read `references/security.md` when the CLI touches external data,
   credentials, or the filesystem; read `references/advanced-patterns.md` only
   when async work, profiles, introspection, delivery sinks, or feedback are
   relevant.
3. **Implement** in whatever language the user chose, applying the spec. Keep
   the output/error/exit-code logic centralized so every command behaves the
   same way.
4. **Verify** with `scripts/probe_cli.py` (see [Audit](#audit)) and tests that
   snapshot help text, JSON shapes, and exit codes.

## Retrofit

1. Read `references/audit.md`, then probe the CLI (`scripts/probe_cli.py`) and
   read the command code for prompts, printing, and exit paths. Read
   `references/output-and-errors.md` and `references/safety-and-mutation.md`
   when assessing those concerns; read `references/security.md` when the CLI
   touches external data, credentials, or the filesystem.
2. List gaps by tier. Blockers first: prompts without a non-interactive path,
   exit 0 on failure, data mixed with logs on stdout.
3. Fix without breaking existing human workflows: keep interactive behavior
   when stdin is a TTY and no flag was given; add flags rather than renaming.
4. Re-probe and confirm every blocker is gone.

## Audit

Read `references/audit.md` for the probe procedure, evidence requirements,
optional linting, and report template. The short version: probe several
subcommands, inspect what the probe cannot see, test retry and malformed-input
paths against throwaway data, and support every finding with evidence and a
concrete fix.

## Reference files

- `references/output-and-errors.md` — JSON contract, stdout/stderr, exit code
  table, error envelope, pagination, `--fields`/`--quiet`, streaming.
- `references/safety-and-mutation.md` — non-interactive rules, `--yes` vs
  `--force` vs confirmation envelope, dry-run, idempotency keys, validation.
- `references/audit.md` — probe procedure, evidence requirements, deeper linting,
  and the audit report template; read for audits and retrofits.
- `references/discoverability.md` — help text template, naming policy,
  stability contract, `AGENTS.md` snippets vs skills, CLI vs MCP.
- `references/security.md` — untrusted output, secrets, hostile input,
  headless auth, resource limits.
- `references/advanced-patterns.md` — `--wait` and job ledgers, profiles,
  introspection command, delivery sinks, feedback; each with caveats.
