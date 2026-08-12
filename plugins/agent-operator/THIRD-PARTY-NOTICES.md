# Third-party notices

This repository learned from and adapted parts of [mattpocock/skills](https://github.com/mattpocock/skills). Rewriting or reducing a file does not erase its provenance.

Of the sixteen current skills:

- zero are near-verbatim copies today;
- five are substantially rewritten direct adaptations;
- seven are independently written with conceptual or structural influence;
- four were authored for this repository without a Matt skill as their source.

The first committed versions of the five direct adaptations were close to the
upstream files. The count above describes the current tree, not an attempt to
rewrite that history.

## Skill lineage

### Direct adaptations, now substantially rewritten

- `architect` began as an adaptation of `codebase-design`. It retains deep
  modules, seams, interface contracts, and design-it-twice. It now adds
  evidence-ranked architecture surveys, lighter treatment of reversible
  decisions, and handoffs into this repository's workflow.
- `diagnose` began as an adaptation of `diagnosing-bugs`. It now uses a shorter
  evidence loop, separates diagnosis from shipping, and reports incomplete
  verification explicitly.
- `review` began as an adaptation of `code-review`. It now reviews a fixed diff
  across correctness, requirements, security, and maintainability.
- `tdd` began as an adaptation of Matt's `tdd` skill. It now focuses on
  observable behavior and public seams, and stops before commits or delivery.
- `unstick` began as an adaptation of `resolving-merge-conflicts`. It now adds
  protected-branch checks, worktree and rebase-state handling, and the exact
  lease rules required by this repository's guard.

These files have been substantially rewritten, but the upstream MIT
attribution remains.

### Conceptual or structural influence

- `navigate` is original prose, with an early metadata string and adversarial-questioning concept influenced by Matt's grilling workflow.
- `prototype` is original prose informed by Matt's prototype rules and sequencing.
- `handoff` uses the same compact cross-session handoff shape, in new words.
- `to-spec` rebuilds Matt's idea of turning a decided conversation into an implementation contract.
- `wizard` rebuilds Matt's human-only setup idea around this repository's credential guard and a constrained runner.
- `research` uses the same distinct primary-source research category. This implementation is written for this repository's evidence and citation contract.
- `domain-modeling` was added after studying Matt's separate domain-modeling category. This implementation is written from scratch around business language, rules, states, and ownership.

### Authored for this repository without a Matt skill as the source

- `bootstrap`
- `breakdown`
- `setup`
- `ship`

`setup` adopts an existing repository's tracker, verification commands, CI, domain documents, and release route. It is not derived from Matt's skill-installer setup workflow.

## Upstream license

The upstream project is licensed under MIT. Its required notice follows.

---

MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
