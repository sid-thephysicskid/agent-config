---
name: architect
description: Design a focused module, interface, seam, or migration, or survey an existing codebase for high-leverage architecture improvements. Use when responsibilities are tangled, invariants are duplicated, a change crosses layers, tests require internal mocking, interfaces leak implementation details, or the user asks how to improve codebase architecture. Use domain-modeling first when the problem language or business rules are unclear.
---

# Architect

Make important behavior easier to change, test, and understand. Choose one mode from the request: **focused design** for a known change or boundary, or **architecture survey** when the user wants improvement candidates but has not selected one.

Read surrounding code, tests, project verification notes, and existing architecture decisions before proposing a new abstraction. If consequential domain terms or rules are contradictory, stop that part and use `/domain-modeling` in Claude Code or `$domain-modeling` in Codex.

## Focused design

Start with the behavior and constraints already decided. Identify:

- responsibilities and explicit non-responsibilities;
- invariants and their single enforcement owner;
- state, failure, concurrency, and transaction boundaries;
- dependencies such as databases, networks, queues, time, and randomness;
- existing code that already owns part of the behavior;
- callers and migration constraints.

Place a seam where behavior genuinely varies or crosses an external boundary. A seam is a place where an implementation can change without callers learning its mechanics. Do not add one around every class.

Prefer a deep module: substantial behavior behind a small interface. Its interface includes everything callers must know: methods, parameters, invariants, ordering, errors, configuration, and important performance behavior. Warning signs of a shallow design include:

- an interface mirrors every method of a dependency;
- callers must coordinate a fragile sequence;
- policy conditions repeat across layers;
- tests mock modules the project owns;
- one behavior change requires unrelated callers to change together.

Run the deletion test: if removing the proposed module only removes forwarding code, it has not earned a seam. One production implementation alone rarely justifies a general abstraction. An external dependency plus a deterministic test substitute can justify a narrow port.

For a costly or hard-to-reverse choice, sketch two materially different designs. Compare interface size, invariant ownership, change locality, failure handling, observability, test surface, migration, and rollback. Recommend one. For a local reversible change, do not manufacture alternatives.

### Focused deliverable

State:

1. the selected responsibilities and seam;
2. the public contract and error behavior;
3. each invariant and its enforcement point;
4. dependency and adapter strategy;
5. tests through the public contract;
6. migration order, compatibility, and rollback;
7. the rejected alternative when design-it-twice applied.

## Architecture survey

Survey to decide where design work would pay off; do not start refactoring merely because the mode found a smell.

Trace several representative changes through the code and gather file-level evidence for:

- change amplification across otherwise unrelated modules;
- scattered invariants or transaction ownership;
- dependency cycles or reversed dependency direction;
- pass-through layers with little leverage;
- tests coupled to internals or requiring excessive mocking;
- error, retry, concurrency, or observability gaps at boundaries;
- duplicated translation between external and domain representations.

Rank candidates by expected reduction in change cost, correctness risk, frequency of the affected work, migration difficulty, and confidence in the evidence. Do not reward diagram neatness, fashionable patterns, raw file size, or speculative future flexibility.

For the top candidates, report:

| Candidate | Evidence | Failure or change cost | Proposed seam or ownership move | Effort and migration risk | Confidence |
|---|---|---|---|---|---|

Recommend at most three candidates and identify the smallest safe first step. Include “leave it alone” when a smell has no demonstrated cost. If the user authorizes an improvement, switch the selected candidate into focused-design mode before implementation.

## Finish

Use a diagram only when it clarifies a non-obvious relationship. Return the decision in the conversation unless the user requested an artifact or the repository has an established ADR convention.

Hand unresolved empirical questions to `/prototype` or `$prototype`, a selected contract to `/tdd` or `$tdd`, and several independently shippable migration slices to `/breakdown` or `$breakdown`.
