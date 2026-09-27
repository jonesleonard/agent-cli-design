# Advanced patterns (situational)

These patterns help CLIs that wrap long-running jobs, heavily configured
APIs, or large command surfaces. None is required for a CLI to be
agent-ready. Recommend one only when the user's CLI has the problem it
solves, and mention its cost.

## Contents

- [Async: --wait and a job ledger](#async---wait-and-a-job-ledger)
- [Profiles](#profiles)
- [Introspection command](#introspection-command)
- [Delivery sinks](#delivery-sinks)
- [Feedback channel](#feedback-channel)
- [Schema-driven generation](#schema-driven-generation)

## Async: --wait and a job ledger

**Problem:** the command submits work and returns a job ID. Agents then
write their own poll loops (burning turns and often getting timing wrong) or
move on before the result exists.

**Pattern:**

```text
$ tool video render --script story.txt --wait --timeout 10m --json
{"job_id": "job_8f2a", "status": "complete", "url": "https://.../out.mp4"}
```

- `--wait` polls with exponential backoff and jitter until a terminal state or
  `--timeout`. On timeout, exit with the transient code and return the job ID
  and current status so the caller can resume.
- Progress goes to stderr; the final result to stdout.
- A `jobs` command group: `jobs list`, `jobs get <id>`, `jobs wait <id>`,
  and optionally `jobs prune`.
- A local ledger (e.g. `~/.local/state/tool/jobs.jsonl`) records submitted
  jobs, so a retried `--wait` after a disconnect can find the in-flight job
  instead of submitting a new one. Pair it with idempotency keys.

**Cost:** local state to manage and keep consistent with the server. If the
server already exposes job listing, prefer querying it over a local ledger.

## Profiles

**Problem:** every invocation repeats the same many flags (account, region,
defaults).

**Pattern:** named bundles of settings.

```text
tool profile save podcast --voice warm-en --webhook https://example.com/hook
tool video create --profile podcast --script ep42.txt
```

- Precedence: explicit flag > env var > profile > config default > built-in.
- Show which values came from where in `--verbose` or `--dry-run` output.
- `profile list/get/save/delete`; store in the platform config dir
  (`$XDG_CONFIG_HOME/tool/` on Linux, the equivalent elsewhere).
- Many CLIs already call this a "context" or "config" (`kubectl config
  use-context`, `gcloud config configurations`); reuse the ecosystem's word.

**Cost:** hidden state. An agent may not know a profile is active. Make the
active profile visible in output and never put secrets in plain-text profiles.

## Introspection command

**Problem:** parsing help text to learn a large CLI's full shape is slow and
lossy.

**Pattern:** a command that prints the command tree, flags, types, enums, and
defaults as versioned JSON:

```text
$ tool schema --json | jq '.commands.post.create.flags'
{"--visibility": {"type": "enum", "values": ["public", "private", "unlisted"]}, ...}
```

- Include a `schema_version` so consumers can detect breaking changes.
- Generate it from the same definitions that build the parser, so it can't
  drift.
- Not yet a widespread convention — agents won't look for it unless help text
  or the `AGENTS.md` snippet mentions it. Name it plainly (`schema`, `commands
  --json`) and link it from top-level help.

**Cost:** one more artifact to keep stable. Worth it for CLIs with dozens of
commands; overkill for small ones, where good `--help` suffices.

## Delivery sinks

**Problem:** the command produces an artifact (file, media, report) and the
agent must shuffle it to where it's needed.

**Pattern:** `--out <path>` writes atomically (temp file + rename) and returns
the path and size in JSON. Some CLIs extend this to a `--deliver` flag with
schemes (`file:`, `stdout`, `webhook:`), refusing unknown schemes with an
error listing supported ones.

**Cost:** webhook delivery turns the CLI into something that sends data to
arbitrary URLs on an agent's say-so. That's an exfiltration and SSRF vector.
Prefer file output; if webhooks are necessary, validate targets and consider an
allowlist configured by the human.

## Feedback channel

**Problem:** agents hit friction (confusing errors, doc mismatches) that
maintainers never hear about.

**Pattern:** `tool feedback "<text>"` appends to a local JSONL file; an
optional, explicitly configured endpoint also receives it.

**Cost:** an agent writing feedback may include file contents, secrets, or
private context. Keep upstream sending opt-in by the human, show what will be
sent, and redact. Local-only is the safe default. Many teams get similar value
from telemetry they already have on error codes.

## Schema-driven generation

Consistency across dozens of commands is hard by hand. Large CLIs (Cloudflare
is rebuilding Wrangler this way) define commands in one schema and generate the
parser, help, JSON shapes, introspection output, docs, SDKs, and MCP tools
from it, with naming rules enforced by lint at the schema layer. For small
CLIs, a test that walks the command tree and checks naming and flag
conventions gets most of the benefit.
