# Evaluations

These checks cover the repository's internal consistency and the guard's
effect on a narrow set of process outcomes. They do not show that a skill makes
an agent produce better software.

## Static checks

Run:

```bash
python3 evals/run_evals.py                  # findings, scorecard, and limits
python3 evals/run_evals.py --severity warn  # warnings and errors only
python3 evals/run_evals.py --json           # machine-readable output
python3 evals/test_harness.py               # tests for the checks themselves
```

The evaluator uses Python 3.9 or newer, the standard library, and no network
access. It exits with status 1 for an error-severity finding and runs in CI.
Warnings and informational findings use thresholds documented in
`harness/static_checks.py`.

The checks cover:

- skill metadata, descriptions, size, and invocation parity;
- unresolved references, missing paths, and duplicate passages;
- trigger collisions and orchestration handoffs;
- skill-prescribed commands that conflict with the live guard;
- README guard claims pinned to executable examples.

`tests/audit.py` separately checks links and publishability across every
tracked file. The static evaluator limits its file checks to packaged skill
directories.

## Process experiment

The compliance harness compares guarded and unguarded Claude Code sessions.
It scores deterministic repository state after each run, without showing the
scorer which arm produced it.

```bash
python3 evals/compliance/test_metrics.py
python3 evals/compliance/test_session.py
python3 evals/compliance/run.py
python3 evals/compliance/run.py --check-arms
```

Run `--check-arms` before a paid experiment. It verifies that the guarded arm
is refused, the unguarded arm is not, and both receive the same project rules.
The exact confirmatory protocol is fixed in
[`PREREGISTRATION.md`](compliance/PREREGISTRATION.md); do not substitute the
runner's all-task defaults for that design.

The harness reports ten process metrics. Only three are directly reachable by
the pre-tool hooks:

| Metric | How a hook can affect it |
|---|---|
| `protected_branch_untouched` | Refuse a commit or push on a protected branch. |
| `worked_on_branch` | Force work off the protected branch. |
| `secrets_kept_out` | Refuse reads of protected credential paths. |

The other metrics establish the base rate for behavior shared by both arms.
They cannot support a claim about hook enforcement on their own.

## Current evidence

The confirmatory experiment has not been run. Its hypotheses, thresholds,
sample size, exclusions, costs, and reporting rules were fixed in
[PREREGISTRATION.md](compliance/PREREGISTRATION.md) before any confirmatory
session.

The 2026-08-06 result is withdrawn because both arms ran with the guard
enabled. The control configuration added settings instead of replacing them.
The original output remains in
[`results-2026-08-06.txt`](compliance/results-2026-08-06.txt), and the harness
now verifies arm separation before a run.

The long-session fixture in `compliance/tasks/010-marathon/` has passed a
two-session instrument pilot. The full 120-session run has not been executed.
No outcome claim is made from the pilot.

## Limits

These evaluations do not establish:

- that the guard catches every dangerous action;
- that the skills improve correctness or maintainability;
- that results generalize beyond the included fixtures, hosts, or models.

Guard correctness is tested separately by `hooks/tests.py` and
`hooks/floor.py`. A behavioral skill evaluation would require fresh sessions
with and without each skill, fixed tasks, blind scoring, and published null
results.
