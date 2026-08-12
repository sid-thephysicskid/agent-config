---
name: review
description: Review a branch, pull request, or working tree for correctness, requirements, security, and maintainability. Use when the user asks for code review, a security pass, release confidence, or an adversarial assessment of changes.
---

# Review

Find defects that can change the decision to ship. Evidence matters more than volume.

## Fix the review scope

Identify the base and head, including committed and uncommitted work when relevant. Read the specification, issue, repository instructions, and tests that define expected behavior. If no specification exists, distinguish user-requested behavior from assumptions.

Do not review an arbitrary snapshot while files are changing. Record the commit or diff boundary you reviewed.

## Review by independent lenses

Use parallel reviewers when the host supports them and the change is large enough to justify it. Otherwise make separate passes so one framing does not hide another.

### Correctness and specification

- Does every requested behavior exist, including failure paths and permissions?
- Did the change add behavior nobody requested?
- Are state transitions, retries, concurrency, and partial failures sound?
- Do migrations work with both old and new application versions during rollout?
- Are tests capable of failing when behavior breaks?

### Security and data safety

- Validate trust boundaries, authorization, input handling, and output encoding.
- Look for secret exposure, unsafe logging, injection, path traversal, request forgery, insecure defaults, and dependency risk.
- Check destructive operations, data retention, privacy, and rollback.
- Treat generated code, CI, scripts, and configuration as executable attack surface.

### Maintainability and operations

- Is each invariant owned once?
- Does the design reuse existing code and platform capability?
- Are interfaces smaller than their implementations and easy to test?
- Are errors observable and actionable?
- Can the change be deployed, monitored, and reversed safely?

## Verify suspicious behavior

Read complete call paths, not only changed lines. Run focused tests or a minimal reproduction when a finding depends on runtime behavior. Consult primary documentation for version-sensitive claims. Do not report a hypothetical as certain.

## Findings

Report findings first, ordered by severity:

- **P0**: active incident, exploitable critical issue, or certain irreversible loss.
- **P1**: likely production failure, security breach, data corruption, or major requirement miss.
- **P2**: real defect with limited impact or a maintainability problem likely to cause future errors.
- **P3**: optional improvement. Keep these few.

Each finding needs a precise location, trigger, impact, evidence, and smallest credible fix. Combine duplicates by root cause. Do not list style preferences as defects when project standards do not require them.

After findings, state open questions, tests run, scope reviewed, and residual risk. If there are no findings, say so plainly and still name what was not verified.

Review does not authorize edits. If the user asked to address findings too, implement them with `/tdd` or `/diagnose` in Claude Code, or `$tdd` or `$diagnose` in Codex, then re-review the final diff.
