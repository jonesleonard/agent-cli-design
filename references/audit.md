# CLI audit procedure

Use this reference for audits and retrofits. It describes the bundled probe,
the evidence standard for findings, and the recommended report structure.

## Probe the CLI

Run the bundled probe against the CLI. It only reads help and passes harmless
flags, but don't point it at a command that mutates on bare invocation:

```bash
uv run scripts/probe_cli.py -- <cli> [subcommand ...]
```

Probe several subcommands, especially list/get and one mutating command with
`--help`. It reports hangs, help/examples presence, JSON validity, ANSI
leakage, unknown-flag handling, and `--version`.

## Inspect what probes cannot see

Read the code or docs for idempotency, dry-run, confirmation handling,
validation, naming consistency, and authentication.

Treat the principles as a floor, not the whole audit. Agents also get hurt by
plain bugs: exercise the tool's own logic with the inputs an agent will send
on a bad day—retries, duplicates (including within one batch), empty and
malformed values, missing files, and partial failures—against a throwaway data
location. Verify every claim in the report against a command you actually ran
or a line of code you read; "X deduplicates" or "Y is idempotent" needs a
demonstration, not an inference.

For a deeper automated pass, suggest
[cli-agent-lint](https://github.com/Camil-H/cli-agent-lint) (34 checks, letter
grade); use its `--no-probe` mode on untrusted CLIs.

## Report structure

```markdown
# Agent-readiness audit: <cli>

## Summary
<2–3 sentences: overall readiness, the single most important fix>

## Blockers
- <finding> — evidence: <command + observed output> — fix: <concrete change>

## Friction
- ...

## Polish
- ...

## What already works
- ...
```

Every finding needs evidence (a command you ran or a line of code) and a
concrete fix. Don't pad with generic advice the CLI already satisfies.
