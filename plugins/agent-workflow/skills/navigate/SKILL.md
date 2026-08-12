---
name: navigate
description: Turn an unclear idea into a decision, or stress-test an existing plan before work starts. Use when the user asks what to build, whether an approach is sound, where to start, or wants a plan challenged.
---

# Navigate

Get from ambiguity to a decision that another engineer can act on. Do not produce a long plan while the important choice is still unresolved.

## Orient

First establish which mode applies:

- **Explore**: the outcome or approach is unclear.
- **Challenge**: a plan exists and needs an adversarial pass.

Read available evidence before asking the user for facts the repo can answer. Separate facts, assumptions, and preferences.

## Explore

Clarify, in this order:

1. Who has the problem and what they cannot do today.
2. What observable outcome would count as success.
3. Constraints that truly bind the solution: time, compatibility, data, security, cost, operations.
4. The smallest slice that tests the value end to end.

Ask one high-leverage question at a time only when the answer materially changes the route. Attach a recommendation and its tradeoff. Do not make the user choose from an unfiltered catalog.

Generate at least two plausible approaches for consequential decisions. Include doing nothing or using an existing capability when credible. Compare total cost, not just implementation effort: maintenance, migration, failure modes, reversibility, and operational burden all count.

## Challenge

Try to break the plan:

- Which assumption has no evidence?
- What existing behavior or user data could it break?
- What happens on partial failure, retry, concurrency, or rollback?
- Which dependency or external system can invalidate the schedule?
- Is the first slice independently useful, or merely one horizontal layer?
- What is being built that could be deleted, reused, or deferred?

Distinguish a fatal flaw from an ordinary risk. Do not inflate every concern into a blocker.

## Finish with a decision

Report:

- the recommended approach and why it wins;
- the smallest useful first slice;
- assumptions that need validation;
- rejected alternatives and why;
- risks, owners, and concrete mitigations;
- the next action.

If talking cannot settle one assumption, hand it to `/prototype`, or `$prototype` in Codex. For an acceptance contract use `/to-spec` or `$to-spec`; for execution use `/breakdown` or `/architect`, or their `$` forms in Codex.
