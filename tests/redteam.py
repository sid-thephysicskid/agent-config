#!/usr/bin/env python3
"""Score candidate commands against the guard, judged on a main-branch fixture.

    python3 tests/redteam.py tests/redteam-candidates.txt
    printf 'git push --force origin main\\n' | python3 tests/redteam.py -

One command per line, `#` for comments. An optional tab-separated expectation:
BLOCK (default), ALLOW, or OPEN: <reason> for a triaged, accepted gap.
Fails on a leak, an over-block, or an OPEN entry that now blocks.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))

import guard_rules  # noqa: E402
from fixtures import MAIN  # noqa: E402


def parse(lines):
    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        expect, why = "BLOCK", ""
        if "\t" in line:
            line, _, tail = line.rpartition("\t")
            tail = tail.strip()
            head = tail.split(":", 1)[0].strip().upper()
            if head in ("ALLOW", "BLOCK", "OPEN"):
                expect = head
                why = tail.split(":", 1)[1].strip() if ":" in tail else ""
        out.append((line.rstrip(), expect, why))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    src = sys.stdin if argv[1] == "-" else open(argv[1])
    cases = parse(src)
    if not cases:
        print("no candidates")
        return 1

    leaked, over, open_, closed = [], [], [], []
    for cmd, expect, why in cases:
        reason = guard_rules.check_command(cmd, MAIN)
        blocked = reason is not None
        if expect == "BLOCK" and not blocked:
            leaked.append(cmd)
        elif expect == "ALLOW" and blocked:
            over.append((cmd, str(reason).split("\n")[0][:70]))
        elif expect == "OPEN":
            (closed if blocked else open_).append((cmd, why))

    print("%d candidate(s)" % len(cases))
    print("  %d leaked        (should have been refused, and untriaged)" % len(leaked))
    print("  %d open          (known, accepted, reason recorded)" % len(open_))
    print("  %d over-blocked  (ordinary work refused)" % len(over))
    if closed:
        print("  %d newly closed  (marked OPEN but now blocked: promote them)"
              % len(closed))

    for cmd in leaked:
        print("\nLEAKED  %s" % cmd)
    for cmd, why in over:
        print("\nOVER-BLOCKED  %s\n              %s" % (cmd, why))
    for cmd, why in closed:
        print("\nNEWLY CLOSED  %s\n              was OPEN: %s" % (cmd, why or "?"))

    if leaked:
        print("\nAdd each leak to tests/cases.py with the incident it encodes,")
        print("then fix the rule. A leak with no case regresses silently.")
        print("If it is not worth fixing, mark it OPEN with a reason, so the")
        print("decision is written down rather than lost in a red number.")
    if closed:
        print("\nA NEWLY CLOSED entry is good news that must not stay OPEN:")
        print("move it to tests/cases.py so it cannot reopen unnoticed.")
    return 1 if (leaked or over or closed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
