# Security policy

## What this is

The guard hooks in `hooks/` are a safety net against agent mistakes, not a
security boundary. Internal errors fail **open**. Analysis timeouts also fail
open unless a cheap scan finds a destructive command shape, in which case the
tool call is refused. Read the [Guard section](README.md#guard) before reporting
anything.

## Worth reporting

- **A bypass.** A command the README's coverage list says is blocked, and is not. The interesting shape is a rule that fires on the plain spelling and misses a sibling one: a quoted refspec, a wrapper word, an environment prefix, a padded command.
- **A guard that fails open on a shape it should handle.** A crash, a hang, or a parse it gives up on, where the rule itself clearly covers the case.

## Not a vulnerability

That a determined human, or an agent that wants to, can work around the guard. That is the stated design, not a defect. The rules are readable and published, and none of it is meant to hold against someone trying. Do not grant permissions you would not grant without these hooks.

## How to report

Use GitHub's private vulnerability reporting: the **Security** tab, then **Report a vulnerability**. Please do not open a public issue for a bypass, because a working bypass is a usable recipe until it is fixed.

Include the exact command string, the working directory it ran from, and what you expected to happen.

## Supported versions

Security fixes are supported on the latest tagged release. If no release is
tagged, audit and pin a commit rather than depending on a moving branch.
