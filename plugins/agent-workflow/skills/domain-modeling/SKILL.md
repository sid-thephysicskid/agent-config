---
name: domain-modeling
description: Establish or repair a software system's domain language, business rules, state transitions, and ownership boundaries. Use when requirements use ambiguous nouns, the same concept has several names, business rules are scattered, an entity lifecycle is unclear, bounded contexts disagree, or a consequential feature needs a domain model before specification or architecture. Do not use merely to reorganize code modules; use architect for that.
---

# Domain Modeling

Make the problem precise before designing the solution. Produce a shared language and explicit rules, not a ceremonial diagram or a class hierarchy.

## Reconstruct the model from evidence

Read the smallest useful set of primary sources:

- user-visible behavior and acceptance criteria;
- code, tests, schemas, events, APIs, and validation rules;
- existing context documents, ADRs, incidents, and support language;
- names used by domain experts or operators.

Treat existing code as evidence, not truth. Record contradictions instead of silently choosing one meaning. Ask only about distinctions that would change behavior or ownership.

## Define the language

For each consequential term, state:

- one precise definition in this context;
- examples and a non-example when confusion is likely;
- identity: what makes two instances the same thing;
- lifecycle or allowed state transitions, if any;
- invariants and the policy or authority that establishes them;
- the context that owns the term.

Prefer the language users and operators already use. Do not introduce domain-driven-design terminology unless it resolves a real ambiguity. Avoid creating one model that forces different contexts to use a word identically; document translations at the boundary instead.

## Model behavior, not database shape

Capture:

1. Actors and the outcomes they seek.
2. Commands or decisions that can change state.
3. Facts or events that have occurred.
4. State transitions, including invalid transitions.
5. Invariants that must hold before and after each transition.
6. Ownership: where a rule is decided and which contexts may only consume the result.
7. Time, retries, concurrency, and failure cases that change the meaning of a rule.

Separate policy from mechanism. For example, “an order may be cancelled only before fulfillment” is a domain rule; an HTTP route and a database transaction are implementation choices for `/architect` or `$architect`.

Use a state table, context map, or event timeline only when it exposes behavior more clearly than prose. Never derive implementation classes mechanically from domain nouns.

## Deliver the smallest durable artifact

Return the model in the conversation unless the user requested a file or the repository already has an established domain-document location. When writing, update that location rather than creating parallel documentation.

A useful model contains:

- a glossary of consequential terms;
- invariants and ownership;
- lifecycle or state transitions;
- context boundaries and translations;
- concrete examples that test the model;
- unresolved questions, each tied to the decision it blocks.

Use an ADR only for a consequential, hard-to-reverse domain decision. Do not bury uncertainty behind invented certainty, and do not claim stakeholder agreement that has not occurred.

## Check the model

Walk at least one normal scenario, one boundary case, and one failure or concurrency case through the proposed language and rules. Confirm that each invariant has one owner and that every state transition names who or what authorizes it.

Finish by distinguishing facts found in the system, decisions made during modeling, and open questions. Hand the result to `/to-spec` or `$to-spec` for a behavioral contract, `/architect` or `$architect` for implementation boundaries, or `/prototype` or `$prototype` when an assumption needs evidence.
