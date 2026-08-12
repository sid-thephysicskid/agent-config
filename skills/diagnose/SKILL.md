---
name: diagnose
description: Find the root cause of a bug, failing test, incident, or performance regression using evidence and controlled experiments. Use when behavior is broken, intermittent, throwing, unexpectedly slow, or not yet understood.
---

# Diagnose

The output is a supported causal explanation. Do not patch the first suspicious line and call it a diagnosis.

## Triage impact first

Determine whether users are currently affected. If this is a live incident, preserve useful evidence and propose the smallest reversible mitigation. Any rollback, feature flag change, scaling action, or production mutation requires the user's approval. Confirm recovery before continuing root-cause work.

For a non-incident, establish scope: first known failure, affected versions or inputs, frequency, recent changes, and expected behavior.

## Build a feedback loop

Reproduce the symptom with the smallest realistic command, request, fixture, benchmark, or test. Record exact inputs and outputs. If it cannot be reproduced, improve observability before guessing: logs, traces, counters, timing, or a targeted diagnostic assertion.

Reduce the search space with evidence:

- compare working and failing states;
- bisect time, configuration, input, or code;
- trace data across boundaries;
- measure before optimizing;
- inspect dependency and environment differences;
- verify assumptions against primary documentation when versions matter.

Keep facts separate from hypotheses.

## Test hypotheses one at a time

For each plausible cause, state what observation would support or reject it. Change one variable and run the feedback loop. Prefer experiments that discriminate between several causes.

Do not stack speculative changes. Do not broaden timeouts, add retries, suppress exceptions, or invalidate caches unless evidence identifies why that is correct. Those moves often hide the symptom while preserving the cause.

## Establish root cause

A root-cause statement connects mechanism to symptom:

```
When <condition>, <mechanism> causes <incorrect state>, which produces <symptom>.
Evidence: <reproduction and discriminating observation>.
```

Ask why the existing design and tests allowed it. The durable fix may be an invariant, contract, or observability improvement rather than another branch.

## Fix only when authorized

If the user asked only for diagnosis, stop with findings and a recommended fix. If the request includes fixing it, add a regression test that fails before the fix, implement the smallest correction, and run the relevant suite. Use `/architect` in Claude Code or `$architect` in Codex when the cause is a misplaced responsibility or broken seam.

For performance work, report baseline, method, variance, and result. A faster single run is not evidence.

## Report

Lead with root cause and confidence. Include reproduction, evidence, contributing factors, fix or recommendation, verification, and remaining uncertainty. Distinguish root cause from incidental cleanup.
