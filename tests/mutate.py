#!/usr/bin/env python3
"""Delete one rule at a time and see whether the suites notice.

    python3 tests/mutate.py

A green suite proves the rules that fire are right. It says nothing about
rules that never fire, or rules whose whole job is already being done by
another rule three files away. Both exist here, and neither is visible from
a passing test run:

  a LEFTOVER  a rule fully subsumed by a later, better one. Deleting it
              changes no verdict. It is dead weight that reads as depth.
  a BLIND     a live rule with no case pinning it. Deleting it silently
              reopens a hole, and the suite stays green.

Removing each row and re-judging the commands it can match finds the UNION of
the two. Telling them apart is a judgement about what the row is for, so the
output asks rather than guesses. It is still the one tool here that can tell a
load-bearing regex from a leftover, which is what makes a refactor reviewable.

It covers the three flat rule tables. The regex-shaped rules and the oversize
signal lists are not mutated, so a clean run means those 41 rows are all
load-bearing, not that every rule in the guard is.

Manual, not a gate: it mutates module state and takes a few minutes. Run it
before and after any change to a rule table.

Python 3.9, stdlib only, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "hooks"))

import cases  # noqa: E402
import floor  # noqa: E402
import guard_git  # noqa: E402
import guard_rules  # noqa: E402
import guard_tools  # noqa: E402
from fixtures import FEAT, MAIN  # noqa: E402

# (module, attribute) for every rule table that is a flat tuple of rows.
TABLES = (
    (guard_git, "DESTRUCTIVE_GIT"),
    (guard_tools, "DESTRUCTIVE_TOOLS"),
    (guard_tools, "PRODUCTION_DEPLOYS"),
)


def corpus():
    """Every command the suites judge, with the cwd and verdict they expect."""
    out = []
    for case in cases.CMD_CASES:
        out.append((case[0], case[1], case[2]))
    for cmd in floor.LIABILITY:
        out.append((cmd if isinstance(cmd, str) else cmd[0], MAIN, True))
    for cmd in floor.ORDINARY:
        out.append((cmd if isinstance(cmd, str) else cmd[0], FEAT, False))
    return out


def verdicts(commands):
    return [guard_rules.check_command(c, cwd) is not None for c, cwd, _ in commands]


def main():
    commands = corpus()
    print("%d rule rows against %d commands\n" % (
        sum(len(getattr(m, a)) for m, a in TABLES), len(commands)))

    before = verdicts(commands)
    leftovers = []

    for module, attr in TABLES:
        rows = getattr(module, attr)
        for i in range(len(rows)):
            mutated = rows[:i] + rows[i + 1:]
            setattr(module, attr, mutated)
            try:
                after = verdicts(commands)
            finally:
                setattr(module, attr, rows)
            changed = [commands[j][0] for j in range(len(commands))
                       if before[j] != after[j]]
            label = "%s[%d]  %s" % (attr, i, str(rows[i][0])[:56])
            if not changed:
                leftovers.append(label)

    print("ROWS NO COMMAND DEPENDS ON  (%d)" % len(leftovers))
    if not leftovers:
        print("  none: every row changes at least one verdict")
    for label in leftovers:
        print("  %s" % label)
    print("\nEach is either a LEFTOVER to delete, or a BLIND with no case.")
    print("Decide by asking what the row matches that nothing else does. If")
    print("the answer is nothing, delete it. If it is something, add the case.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
