# Safety, mutation, and non-interactive execution

## Contents

- [Non-interactive execution](#non-interactive-execution)
- [Flag vocabulary: --yes, --force, --confirm](#flag-vocabulary---yes---force---confirm)
- [Choosing a confirmation model](#choosing-a-confirmation-model)
- [Confirmation envelope protocol](#confirmation-envelope-protocol)
- [Reversibility and real enforcement](#reversibility-and-real-enforcement)
- [Dry run](#dry-run)
- [Idempotency and retries](#idempotency-and-retries)
- [Input validation](#input-validation)

## Non-interactive execution

An agent's shell usually has stdin closed or attached to nothing. A prompt in
that situation either hangs forever or reads EOF and does something
surprising. Rules:

- **Every prompt has a flag equivalent.** Wizards, pickers, and "Which
  environment?" menus all map to flags, env vars, or an input file.
- **Detect non-interactive contexts** and never prompt in them: stdin is not a
  TTY, `CI` is set, or an explicit `--no-input`/`--non-interactive` flag was
  given. Pick one flag name for the explicit switch.
- **In a non-interactive context with missing input, fail fast** with a usage
  error naming the flag. Don't silently pick a default for anything
  consequential.
- **Keep the interactive path for humans** when stdin is a TTY and flags are
  missing. Interactive should be the fallback when flags are absent, not the
  only route.
- **Never open a browser, pager, or editor** without a TTY. Respect `PAGER`
  and disable paging when stdout isn't a terminal (`git` and `gh` both do this).
- **Watch for hidden prompts**: credential helpers, SSH host-key checks,
  package manager confirmations, and "update available, install now?" nags.

TTY detection is a heuristic. Some harnesses run commands under a
pseudo-terminal, so a TTY may be present with nobody at it. That's why the
explicit flag must always exist and why prompts should have a timeout-free
flag path, not just auto-detection.

## Flag vocabulary: --yes, --force, --confirm

These mean different things; keeping them distinct is what makes them safe.

| Flag | Meaning | Precedent |
| --- | --- | --- |
| `--yes`, `-y` | Answer "yes" to confirmation prompts. Does not change what the command is allowed to do. | `apt -y`, `npm init -y`, `gcloud --quiet` |
| `--force`, `-f` | Override a safety check: overwrite existing, delete non-empty, proceed despite conflict or dirty state. | `rm -f`, `git push --force`, `cp -f` |
| `--confirm` | Execute a mutation that was previously described by a confirmation envelope. | Arcjet CLI |
| `--dry-run` | Describe what would happen; change nothing. | `kubectl`, `terraform plan`, `rsync -n` |

Some prominent CLIs use `--force` to mean "skip confirmation" (Cloudflare's
newer schema rules do). If you're matching an ecosystem that already does
this, follow it consistently, but for new tools, keep "don't ask" and "ignore
guards" separate. An agent that adds `--force` to get past a prompt shouldn't
also unknowingly disable an overwrite check.

Avoid bespoke names like `--skip-confirmations`, `--no-prompt`, or
`--assume-yes` unless your ecosystem already uses them.

## Choosing a confirmation model

| Situation | Model |
| --- | --- |
| Read-only command | None |
| Local, reversible, or cheap mutation (create a draft, tag a local file) | Just do it. Maybe `--dry-run`. |
| Destructive but scoped, and callers are trusted automation | Prompt on TTY; require `--yes` otherwise; exit 2 naming `--yes` if missing |
| Production-affecting, irreversible, costly, or security-relevant | Confirmation envelope; also offer `--dry-run` |

The confirmation model is not an authorization system. The server must still
check permissions. It's a guardrail against accidental and poorly reasoned
actions by a caller who has the permission.

## Confirmation envelope protocol

For high-stakes mutations, the command refuses to act without `--confirm`,
exits with a dedicated code, and prints a description of the change plus the
exact command to run:

```text
tool rules update --site site_2abc --rule r_9 --mode block
```

```json
{
  "status": "confirmation_required",
  "command": "rules update",
  "changes": [
    "Rule r_9 on site site_2abc: mode dry_run -> block",
    "Affects ~12,000 requests/hour based on the last 24h"
  ],
  "confirm_command": "tool rules update --site site_2abc --rule r_9 --mode block --confirm"
}
```

Exit code: the documented "confirmation required" code (e.g. 10).

The agent shows `changes` to the user and, on approval, runs
`confirm_command` verbatim. The human stays in the loop without anyone typing
into a prompt, and CI can pass `--confirm` explicitly.

Tips:

- Put the envelope on stdout (it's the command's result) and mention in help
  that the command needs `--confirm`.
- Make `changes` concrete: counts, before/after values, names of affected
  resources.
- Every approval-gated response carries the change description, including
  the highest-risk path. If prod destroys go to an out-of-band human approval
  instead of `--confirm`, the `approval_required` response and the approval
  request itself still list exactly what will be destroyed — a human can't
  meaningfully approve "destroy cluster X" without seeing its size, data, and
  dependents.
- If state can drift between preview and confirm, include a precondition token
  (`--if-match <etag>`) in `confirm_command` so the confirm fails cleanly if the
  world changed.

## Reversibility and real enforcement

Confirmation designs reduce accidents, but every one of them — `--yes`,
`--confirm`, "type the resource name to confirm" — can be satisfied by an
agent that decides to. When the requirement is "an agent must not be able to
do X on its own", the answer lives outside the CLI's flags:

- **Scoped credentials.** Agents run with tokens that lack the dangerous
  permission; the server refuses. Distinct agent identities make this
  auditable.
- **Server-side policy and approval.** For the most dangerous actions the CLI
  can only *request* the action; a human approves out of band (ideally with
  MFA), and the CLI returns a pending state and exits with a documented code.
- **Deletion protection.** A flag on the resource itself that must be
  removed in a separate, auditable step before deletion works.
- **Recoverability.** Soft delete with a grace period, a final automatic
  snapshot/backup, or delayed execution. A mistake that can be undone is
  much cheaper than one that can't.
- **Harness permissions** (e.g. Claude Code permission rules denying
  `dbctl cluster destroy*`) are a useful extra layer, not a boundary; commands
  can be rephrased or run through scripts.

Say this plainly when a user asks how to stop an agent from doing something
destructive; otherwise they may ship a confirmation flag believing it's a
security control.

## Dry run

`--dry-run` must be free of side effects and should return the same shape of
information a real run would, marked as a preview:

```json
{
  "dry_run": true,
  "changes": [
    {"action": "update", "resource": "deployment/web", "field": "image", "from": "web:v2.0", "to": "web:v2.1"},
    {"action": "restart", "resource": "pod/web-*", "count": 3}
  ],
  "warnings": ["3 pods will restart"]
}
```

"Would deploy web" in prose is better than nothing but gives the agent nothing
to verify. Dry run should run the same validation as a real run, so a clean dry
run means the real run won't fail on input.

## Idempotency and retries

Agents retry after timeouts, lost connections, and context resets, often
without knowing whether the first attempt landed.

Strategies, best first:

1. **Declarative commands**: `apply`, `ensure`, `sync`, `set`. Running twice
   converges to the same state and reports `"changed": false` the second time.
   (`kubectl apply` is the model.)
2. **Natural keys**: resources identified by a user-chosen name. `create
   --name prod` returns the existing resource or a distinct conflict code.
   Offer `--if-not-exists` to make that a success.
3. **Idempotency keys**: `--idempotency-key <uuid>` (Stripe's pattern). The
   server or a local ledger returns the original result for a repeated key.
   The agent generates the key once and reuses it on retry.
4. **Detectable conflict**: if none of the above is possible, at least exit
   with the conflict code and include the existing resource's ID.

Avoid deduplicating on content alone ("same text posted twice must be a
retry"). Two identical creates can be legitimate, and silent merging is worse
than a duplicate the user can see.

Deletes should be idempotent too: deleting something already gone should exit
0 with `"changed": false` (or offer `--ignore-missing`), so a retried delete
doesn't look like a failure.

For async operations, idempotency has to cover submit → poll → collect. See
the job ledger in `advanced-patterns.md`.

## Input validation

Agents hallucinate IDs, paste URLs into ID fields, mix up similar-looking
identifiers, and carry invisible characters from copied context. Validate
locally before any network call or side effect:

- **Typed/prefixed IDs** (`site_…`, `team_…`) let you reject an ID of the
  wrong kind immediately. If your IDs are opaque UUIDs, you can't; consider
  prefixes when you control the API.
- **Enums** checked against the valid set, reported in the error.
- **Ranges** for numbers and durations.
- **Paths**: resolve and check they stay within the expected root when the
  CLI writes files; reject `..` escapes where they make no sense.
- **Control characters and newlines** in names, IDs, and header-bound values:
  reject them.
- **Unknown flags and commands are hard errors.** Never ignore unknown flags,
  and never auto-run a fuzzy match. Listing close matches in the error message
  is fine.
