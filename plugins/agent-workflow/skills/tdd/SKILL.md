---
name: tdd
description: Implement behavior test-first in small red, green, refactor cycles. Use for business logic, bug fixes with reproducible behavior, integration tests, or when the user requests TDD or regression coverage.
---

# Test-Driven Development

Use tests to discover and preserve behavior, not to mirror implementation.

## Choose the observable seam

Read the relevant code and existing tests. State the public behavior and the seam where a caller observes it. Prefer the highest-level seam that is fast, deterministic, and precise enough to diagnose failures.

Mock only boundaries the process does not control, such as external APIs, clocks, randomness, and sometimes storage. Avoid mocking the project's own modules. If testing requires extensive internal mocking, use `/architect` in Claude Code or `$architect` in Codex to improve the seam.

## Red

Write one focused test for one behavior. Use an independently known expected result from the specification, a worked example, or a reproduced bug. Run it and confirm it fails for the intended reason.

A test that passes before the change proves nothing. A test that fails from setup or an unrelated error is not red yet.

For a bug, reproduce the reported failure before changing implementation. For an external interaction, assert the behavior at the adapter boundary and use a controlled fake or local test service.

## Green

Implement the smallest complete behavior that makes the test pass. Do not add speculative cases, abstractions, or configuration. Run the focused test, then the nearest relevant suite.

## Refactor

Improve names, duplication, and structure while green. Re-run tests after each meaningful change. If the refactor changes a public contract or moves a major boundary, stop and use `/architect` in Claude Code or `$architect` in Codex.

Repeat one vertical behavior at a time. Do not write a large batch of imagined tests before learning from the first implementation.

## Test quality checks

A durable test:

- describes behavior in domain language;
- uses public interfaces rather than private methods;
- fails when the behavior is deliberately broken;
- is deterministic and independent of execution order;
- covers the important failure path as well as success;
- does not assert incidental formatting, call counts, or object shape unless they are contractual.

Property tests, examples, and integration tests are all valid when they fit the risk. Do not force TDD onto mechanical configuration or generated artifacts where a post-change validation is clearer. State that exception rather than pretending a test came first.

## Finish

Run the relevant project checks. Report the seam, the red failure observed, the behavior added, and any untested risk. Do not commit from this skill. Hand finished work to `/review` or `/ship` in Claude Code, or `$review` or `$ship` in Codex.
