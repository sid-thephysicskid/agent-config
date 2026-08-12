---
name: prototype
description: Build a deliberately disposable experiment to answer one unresolved technical or product question. Use when evidence from a small implementation will resolve uncertainty faster than more planning.
---

# Prototype

A prototype buys evidence. It does not quietly become production code.

## Define the experiment

Write down:

- the single question;
- the hypothesis;
- the observable result that supports or rejects it;
- the time or scope limit;
- what the prototype deliberately will not handle.

If there is no falsifiable question, use `/navigate` in Claude Code or `$navigate` in Codex instead.

## Isolate it

Use a new branch or disposable worktree. Do not edit the primary branch. Reuse the real stack where that affects the answer, but omit production hardening unrelated to the hypothesis.

Mark shortcuts beside the code with the condition that would require revisiting them. Never use real credentials or production data. Do not deploy, publish, push, or open a PR unless the user explicitly asks to share the experiment.

## Build only the measuring instrument

Implement the thinnest end-to-end path that can answer the question. Add logging, timings, fixtures, or a tiny test harness when they produce the evidence. Do not add extensibility, generalized abstractions, polished UI, broad tests, or documentation unless one is part of what the experiment measures.

Run the experiment more than once when noise could change the conclusion. Preserve raw measurements needed to verify the finding.

## Report and stop

Return:

- hypothesis and result;
- evidence and how it was measured;
- limitations;
- the decision this supports;
- what, if anything, is worth carrying into production.

Treat the prototype code as contaminated by shortcuts. Ask whether to delete it or retain the branch for reference. Hand the finding to `/architect` or `$architect` for a production design, or to `/tdd` or `$tdd` when the production seam is clear. Production work starts clean; it does not continue by polishing the prototype in place.
