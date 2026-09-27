# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Probe a CLI for common agent-readiness problems.

Runs a handful of invocations (<target> --help, <root> --version,
<root> --unknown-flag, and optionally <target> --json) with stdin held open
and no TTY, then reports findings as JSON on stdout.

A CLI that ignores --help will run the target for real, so only point this at
commands that are safe to invoke bare.

Usage:
  uv run probe_cli.py [--timeout S] [--run] [--run-args "..."] -- <cli> [subcommand ...]

Examples:
  uv run probe_cli.py -- gh pr
  uv run probe_cli.py --run --run-args "--limit 1" -- gh pr list
  uv run probe_cli.py --timeout 3 -- python mytool.py user list

Exit codes: 0 no failures, 1 at least one failed check, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
EXAMPLES_RE = re.compile(
    r"^\s*(examples?|usage examples?)\s*:?\s*$", re.IGNORECASE | re.MULTILINE
)
USAGE_RE = re.compile(r"\busage\b", re.IGNORECASE)
JSON_FLAG_RE = re.compile(
    r"--json\b|--output[ =]\S*json|--format[ =]\S*json|-o json", re.IGNORECASE
)
SUGGEST_RE = re.compile(r"did you mean", re.IGNORECASE)
VERSION_RE = re.compile(r"\d+\.\d+")
UNKNOWN_FLAG = "--definitely-not-a-real-flag-7f3a"


@dataclass
class Run:
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

    def evidence(self, limit: int = 300) -> dict:
        return {
            "argv": shlex.join(self.argv),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "stdout_head": self.stdout[:limit],
            "stderr_head": self.stderr[:limit],
        }


@dataclass
class Check:
    id: str
    status: str  # pass | warn | fail | skip
    detail: str
    evidence: dict = field(default_factory=dict)


def run(argv: list[str], timeout: float) -> Run:
    """Run with stdin as an open pipe nobody writes to, like an agent shell.

    The write end stays open until the process exits, so a prompt blocks
    (and times out) instead of reading EOF.
    """
    env = {k: v for k, v in os.environ.items() if k not in {"NO_COLOR", "CI"}}
    env.setdefault("TERM", "xterm-256color")  # tempt color output to detect leakage
    stdin_r, stdin_w = os.pipe()
    try:
        proc = subprocess.Popen(
            argv,
            stdin=stdin_r,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            errors="replace",
        )
    except FileNotFoundError:
        os.close(stdin_w)
        return Run(argv, None, "", f"executable not found: {argv[0]}", False)
    finally:
        os.close(stdin_r)
    try:
        out, err = proc.communicate(timeout=timeout)
        return Run(argv, proc.returncode, out, err, False)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return Run(argv, None, out or "", err or "", True)
    finally:
        os.close(stdin_w)


INTERPRETERS = re.compile(r"^(python\d*(\.\d+)?|node|bun|deno|ruby|perl|php)$")


def root_command(target: list[str]) -> list[str]:
    """The CLI itself without subcommands; keeps the script path for interpreters."""
    if INTERPRETERS.match(os.path.basename(target[0])) and len(target) > 1:
        return target[:2]
    return target[:1]


def check_hang(r: Run, label: str) -> Check | None:
    if r.timed_out:
        return Check(
            f"no_hang:{label}",
            "fail",
            "Command did not exit within the timeout with stdin open and no TTY; "
            "likely waiting on a prompt, pager, or browser.",
            r.evidence(),
        )
    return None


def check_ansi(runs: list[Run]) -> Check:
    leaks = [r for r in runs if ANSI_RE.search(r.stdout) or ANSI_RE.search(r.stderr)]
    if leaks:
        return Check(
            "no_ansi_when_piped",
            "fail",
            "ANSI escape codes emitted although output is not a TTY.",
            leaks[0].evidence(),
        )
    return Check("no_ansi_when_piped", "pass", "No ANSI escapes in piped output.")


def probe(
    target: list[str], timeout: float, run_data: bool, run_args: list[str]
) -> list[Check]:
    checks: list[Check] = []
    runs: list[Run] = []

    help_run = run([*target, "--help"], timeout)
    runs.append(help_run)
    if help_run.exit_code is None and not help_run.timed_out:
        return [Check("executable", "fail", help_run.stderr, help_run.evidence())]
    if hang := check_hang(help_run, "help"):
        checks.append(hang)
    else:
        text = help_run.stdout or help_run.stderr
        if help_run.exit_code == 0 and help_run.stdout.strip():
            checks.append(
                Check("help_ok", "pass", "--help exits 0 and prints to stdout.")
            )
        elif help_run.exit_code == 0:
            checks.append(
                Check(
                    "help_ok",
                    "warn",
                    "--help exits 0 but prints to stderr.",
                    help_run.evidence(),
                )
            )
        else:
            checks.append(
                Check("help_ok", "fail", "--help exits non-zero.", help_run.evidence())
            )
        checks.append(
            Check(
                "help_usage_line",
                "pass" if USAGE_RE.search(text) else "warn",
                "Usage line present."
                if USAGE_RE.search(text)
                else "No usage line found in help.",
            )
        )
        has_examples = bool(EXAMPLES_RE.search(text))
        checks.append(
            Check(
                "help_examples",
                "pass" if has_examples else "warn",
                "Help includes an Examples section."
                if has_examples
                else "No Examples section; agents adapt examples more reliably than prose.",
            )
        )
        has_json = bool(JSON_FLAG_RE.search(text))
        checks.append(
            Check(
                "help_mentions_json",
                "pass" if has_json else "warn",
                "Help documents a JSON output flag."
                if has_json
                else "Help does not mention --json/--output json (fine if this is a pure group command).",
            )
        )

    version_run = run([*root_command(target), "--version"], timeout)
    runs.append(version_run)
    if hang := check_hang(version_run, "version"):
        checks.append(hang)
    elif version_run.exit_code == 0 and VERSION_RE.search(
        version_run.stdout + version_run.stderr
    ):
        checks.append(Check("version", "pass", "--version works."))
    else:
        checks.append(
            Check(
                "version",
                "warn",
                "--version missing or failing on the root command.",
                version_run.evidence(),
            )
        )

    # Root only: a sloppy parser could treat the flag as a positional and run a
    # subcommand for real.
    bad_run = run([*root_command(target), UNKNOWN_FLAG], timeout)
    runs.append(bad_run)
    if hang := check_hang(bad_run, "unknown_flag"):
        checks.append(hang)
    elif bad_run.exit_code == 0:
        checks.append(
            Check(
                "unknown_flag_rejected",
                "fail",
                "Unknown flag accepted with exit 0; agents can't detect typos or hallucinated flags.",
                bad_run.evidence(),
            )
        )
    else:
        checks.append(
            Check(
                "unknown_flag_rejected",
                "pass",
                f"Unknown flag rejected (exit {bad_run.exit_code}).",
            )
        )
        if bad_run.exit_code != 2:
            checks.append(
                Check(
                    "usage_exit_code",
                    "warn",
                    f"Usage error exits {bad_run.exit_code}; 2 is the common convention.",
                    bad_run.evidence(),
                )
            )
        if bad_run.stdout.strip() and not bad_run.stderr.strip():
            checks.append(
                Check(
                    "errors_on_stderr",
                    "warn",
                    "Usage error printed to stdout, not stderr.",
                    bad_run.evidence(),
                )
            )
        if SUGGEST_RE.search(bad_run.stdout + bad_run.stderr):
            checks.append(
                Check(
                    "no_fuzzy_autocorrect",
                    "warn",
                    "Error offers 'did you mean'. Fine as a hint; verify the CLI never auto-runs the guess.",
                    bad_run.evidence(),
                )
            )

    if run_data:
        data_run = run([*target, *run_args, "--json"], timeout)
        runs.append(data_run)
        if hang := check_hang(data_run, "data"):
            checks.append(hang)
        elif data_run.exit_code != 0:
            checks.append(
                Check(
                    "json_output",
                    "warn",
                    "Data command with --json exited non-zero; check whether the flag is spelled differently.",
                    data_run.evidence(),
                )
            )
        else:
            try:
                json.loads(data_run.stdout)
                checks.append(
                    Check(
                        "json_output",
                        "pass",
                        "--json produced a single valid JSON document on stdout.",
                    )
                )
            except json.JSONDecodeError:
                lines = [ln for ln in data_run.stdout.splitlines() if ln.strip()]
                try:
                    for ln in lines:
                        json.loads(ln)
                    ok = bool(lines)
                except json.JSONDecodeError:
                    ok = False
                checks.append(
                    Check(
                        "json_output",
                        "pass" if ok else "fail",
                        "--json produced valid JSON Lines."
                        if ok
                        else "--json stdout is not valid JSON; data may be mixed with logs.",
                        {} if ok else data_run.evidence(),
                    )
                )
    else:
        checks.append(
            Check(
                "json_output",
                "skip",
                "Pass --run to execute a data command with --json (only on read-only commands).",
            )
        )

    checks.append(check_ansi(runs))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="probe_cli.py",
        description="Probe a CLI for agent-readiness problems. Output is JSON on stdout.",
        epilog="Examples:\n  uv run probe_cli.py -- gh pr\n  uv run probe_cli.py --run --run-args '--limit 1' -- gh pr list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="seconds per invocation before declaring a hang (default: 5)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="also run the target with --json; use only on read-only commands",
    )
    parser.add_argument(
        "--run-args",
        default="",
        help="extra args for the --run invocation, as one shell-quoted string",
    )
    parser.add_argument(
        "target", nargs="+", help="the CLI and subcommand to probe, after --"
    )
    args = parser.parse_args()

    checks = probe(args.target, args.timeout, args.run, shlex.split(args.run_args))
    counts = {
        s: sum(c.status == s for c in checks) for s in ("pass", "warn", "fail", "skip")
    }
    json.dump(
        {
            "target": shlex.join(args.target),
            "summary": counts,
            "checks": [asdict(c) for c in checks],
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
