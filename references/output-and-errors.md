# Output, errors, and exit codes

## Contents

- [Streams](#streams)
- [JSON output](#json-output)
- [Success payloads](#success-payloads)
- [Exit codes](#exit-codes)
- [Error envelope](#error-envelope)
- [Bounding output](#bounding-output)
- [Streaming and long output](#streaming-and-long-output)

## Streams

stdout is the API. Anything a caller might parse goes there, and nothing else
does. stderr gets progress, spinners, warnings, deprecation notices, debug
logs, and human error text.

A quick test: `tool list --json 2>/dev/null | jq .` must always succeed when
the command succeeds, and `tool list --json | wc -l` must not change because a
warning was printed.

Disable ANSI color and animations when:

- stdout (for data) or stderr (for progress) is not a TTY,
- `NO_COLOR` is set to any non-empty value (see <https://no-color.org>),
- `TERM=dumb`, or `--no-color` is passed.

Spinners that redraw with `\r` produce kilobytes of garbage in captured
output. Suppress them entirely when stderr isn't a TTY.

## JSON output

- **One flag, everywhere.** Every data-returning command supports the same
  flag. Commands that return nothing useful should still emit a small JSON
  result in JSON mode (`{"ok": true, "id": "..."}`) so callers don't special-case.
- **Stable names, consistent types.** A field is always the same type across
  commands: timestamps as ISO 8601 strings in UTC, durations as numbers with
  the unit in the name (`duration_s`, `size_bytes`), enums in a single case.
  Never `"3 days"` in one place and `259200` in another.
- **Lists:** prefer an object wrapper over a bare array so you can add
  pagination metadata later without breaking callers:
  `{"items": [...], "next_cursor": "abc", "truncated": true}`.
- **Null vs absent:** pick one policy for "no value" and keep it.
- **Deterministic order:** sort lists by a documented key. Unstable ordering
  makes agents think state changed.
- **Single document per invocation** unless you're streaming (see below).

`--json` output is the contract; the human table is not. It's fine for the
human view to change; the JSON shape changes additively only.

## Success payloads

Return what the next step needs. After a mutation, include the resource ID,
its canonical URL if one exists, the resulting state, and whether anything
actually changed:

```json
{"id": "dep_abc123", "status": "deployed", "url": "https://staging.example.com", "changed": true, "duration_s": 34}
```

"✓ Deployed!" with no ID forces a follow-up `list` call and a guess.

## Exit codes

No universal standard exists. This table is a reasonable default; the
important part is documenting yours and keeping it stable.

| Code | Meaning | Agent's typical reaction |
| --- | --- | --- |
| 0 | Success (including idempotent no-op) | Continue |
| 1 | General / unexpected error | Read error, maybe report |
| 2 | Usage error: unknown flag, missing arg, invalid value | Fix invocation, retry once |
| 3 | Not found | Check the ID, list resources |
| 4 | Auth / permission error | Stop, ask for credentials |
| 5 | Conflict / already exists / precondition failed | Fetch existing, skip, or reconcile |
| 6 | Transient: timeout, rate limited, service unavailable | Back off and retry |
| 10 | Confirmation required (if using a confirmation envelope) | Show changes to user, rerun with `--confirm` |

Notes:

- 2 for usage errors matches argparse, Click, and shell builtins. Some
  frameworks (Cobra) default to 1 — override it.
- The transient-vs-permanent split is the most valuable distinction: it tells
  the agent whether retrying can possibly help.
- `sysexits.h` (64–78) is an alternative with prior art; it's fine if you
  already use it, but few agents know it by heart.
- Codes above 125 collide with shell signal conventions (126, 127, 128+N).
- Partial failure (3 of 5 items succeeded) is a failure exit, with per-item
  results in the JSON body.

## Error envelope

In JSON mode, write errors as JSON to stderr (and keep stdout empty or also
JSON, but pick one and document it). Include a stable machine code, the human
message, the offending input, and a remediation:

```json
{
  "error": {
    "code": "invalid_value",
    "message": "--visibility must be one of: public, private, unlisted",
    "field": "--visibility",
    "value": "secret",
    "valid_values": ["public", "private", "unlisted"],
    "hint": "tool post create --visibility private --content 'hi'",
    "retryable": false
  }
}
```

In text mode the same information reads naturally:

```text
error: --visibility must be one of: public, private, unlisted (got "secret")
  try: tool post create --visibility private --content 'hi'
```

Guidelines:

- **Enumerate when the domain is small.** Enums, known regions, resource types.
  When the set is large or dynamic, point to the command that lists it
  (`see: tool region list`).
- **Echo the input.** The agent needs to see what it actually sent — quoting
  and variable expansion often differ from what it intended.
- **No stack traces by default.** Put them behind `--verbose` or a debug env var.
- **Validate before side effects.** Parse and check everything, then act. A
  failure halfway through a multi-step mutation is much harder to recover
  from.
- **Missing required flag in non-interactive mode** is a usage error (2) that
  names the flag, not a prompt.

## Bounding output

Context windows are finite and every byte of output is paid for.

- **List defaults:** a modest default page size (20–100) and an explicit
  `--limit`. `--limit 0` or `--all` for everything, opt-in.
- **Say when you truncated.** Include `"truncated": true` and a hint about how
  to narrow (`--filter`, `--since`) or continue (`--cursor`).
- **Field selection:** `--fields id,name,status` for JSON output.
- **Bare values:** `--quiet`/`-q` prints one identifier per line, no headers —
  ideal for `xargs` and `while read`.
- **Server-side filters** beat client-side `jq` because they shrink both
  transfer and output: `tool pod list --status failed`.
- **Summaries before detail:** `get` returns the common fields; `get --full`
  or `describe` returns everything.
- **Logs and blobs:** tail by default (`--tail 100`), or write to a file and
  return its path and size.

## Streaming and long output

For commands that produce incremental results (watch, tail, bulk operations),
use JSON Lines: one complete JSON object per line, flushed per line. Each line
should be independently parseable and carry a `type` or `event` field when
more than one kind of record appears. End with a summary record so the caller
knows the stream finished normally rather than being cut off.
