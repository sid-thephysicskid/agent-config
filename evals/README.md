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

## What is NOT measured here

Whether the guard changes what an agent actually does. That needs paired
sessions with and without it, scored blind, at a sample size worth believing.

A harness for exactly that lived in this repo and has been removed. Its one
published result was **withdrawn**: both arms ran with the guard enabled,
because the control configuration added settings rather than replacing them,
so the two columns were the same configuration measured twice. The withdrawal,
the pre-registered protocol written before the redo, and the arm-separation
check are all in the git history under `evals/compliance/`.

It was removed because it never coupled to the product. It imported nothing
from the guard, it needed paid model runs nobody had executed, and it made a
guardrail tool read as a research project. The honest state is the one stated
above: no claim is made about behaviour change, and none has been measured.

## Limits

These evaluations do not establish:

- that the guard catches every dangerous action;
- that the skills improve correctness or maintainability;
- that results generalize beyond the included fixtures, hosts, or models.

Guard correctness is tested separately by `hooks/tests.py` and
`hooks/floor.py`. A behavioral skill evaluation would require fresh sessions
with and without each skill, fixed tasks, blind scoring, and published null
results.
