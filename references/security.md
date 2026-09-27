# Security for agent-driven CLIs

An agent runs your CLI with the user's credentials, feeds its output back into
its own reasoning, and may be steered by text it read elsewhere. That changes
the threat model compared with a human at a terminal.

## Output is agent input

Everything the CLI prints becomes part of the agent's context. If the CLI
prints data that someone else controls — issue bodies, commit messages, web
pages, log lines, file contents, API error messages from third parties — that
text can contain instructions aimed at the agent ("ignore previous
instructions and run …").

- In JSON mode, keep untrusted content in clearly named data fields
  (`"body": "..."`), never mixed into `message` or `hint` fields that agents
  treat as guidance from the tool.
- Don't echo third-party text into error remediation strings.
- Consider a flag to omit large free-text fields (`--fields`) so agents fetch
  only what they need.
- Strip or escape terminal control sequences from untrusted text in human
  output; they can rewrite what a human sees.

## Secrets

- Never print tokens, passwords, or full credentials in normal output, error
  messages, `--verbose` logs, or dry-run previews. Show a redacted form
  (`tok_****a1b2`).
- Accept secrets from env vars, files, or stdin rather than flags, because
  flags land in shell history and process listings and agents log their
  commands.
- Config and credential files the CLI writes should be created with
  user-only permissions.

## Hostile or mistaken input

- Reject control characters, newlines, and NUL in identifiers and values that
  end up in URLs, headers, file names, or logs.
- Resolve paths and refuse to write outside the intended directory; be careful
  with symlinks.
- Never pass user input through a shell. Build argv arrays.
- Validate URL schemes and hosts when the CLI fetches or posts to a
  caller-supplied URL (webhooks, imports). Consider an allowlist; block
  link-local and metadata addresses where relevant.

## Headless auth

- Token env var (e.g. `TOOL_TOKEN`) takes precedence over stored credentials,
  so CI and sandboxed agents never need a browser.
- Support scoped, least-privilege tokens so users can give an agent less power
  than they have.
- Auth errors use their own exit code and say how to authenticate, without
  starting an interactive login.

## Resource limits

- `--timeout` on anything that waits on the network, with a sensible default.
- Surface rate limiting explicitly (transient exit code, `retry_after_s` in the
  error) so agents back off instead of hammering.
- Bound retries inside the CLI; don't let an internal retry loop run forever.

## Guardrails are not authorization

`--dry-run`, `--yes`, and confirmation envelopes reduce accidents. They don't
replace server-side permission checks and validation, which must still be
enforced.
