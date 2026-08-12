#!/usr/bin/env python3
"""Put candidate commands through the live guard and report what got through.

    python3 evals/redteam.py candidates.txt
    printf 'git push --force origin main\\n' | python3 evals/redteam.py -

One command per line. A line starting with `#` is a comment. A line may carry a
tab and an expectation; the default is BLOCK.

    ALLOW           legitimate work that must NOT be blocked
    OPEN: <reason>  known to get through, triaged, and accepted for now

Three outcomes, and the third exists because of what this file became:

    LEAKED   should have been refused, was not, and nobody has looked at it
    OPEN     should have been refused, was not, and someone wrote down why
    BLOCKED  ordinary work the guard refused, which is how a guard gets
             switched off, and a switched-off guard protects nothing

**Only LEAKED and BLOCKED fail.** For months this file reported 74 of 98
leaking and exited non-zero every time, so the number stopped meaning anything
and nobody triaged it. A corpus that is always red is the same as a corpus that
is always green: neither tells you whether today is worse than yesterday. An
OPEN entry has to carry a reason, so the accepted list can be read and argued
with rather than accumulating in silence.

This is the scoring half. Generating good candidates is the other half and is
not automated here: an adversarial model is better at inventing phrasings than
any list I could write down, and the interesting ones came from asking one to
try. Feed its output in, and put whatever leaks into `hooks/cases.py` so it can
never leak twice.

Every candidate is judged with cwd = MAIN, a fixture checked out on a
protected branch. That is deliberate, because most of the corpus is about
protected-branch rules, but it means a candidate can block for a reason that
has nothing to do with what it was written to test: `git push --for\\ce` blocks
on main because it is a push on main, not because the escaped flag was
recognised. Read a block here as "something refused it", never as "the rule you
had in mind refused it".

Python 3.9, stdlib only, no network.
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
        print("\nAdd each leak to hooks/cases.py with the incident it encodes,")
        print("then fix the rule. A leak with no case regresses silently.")
        print("If it is not worth fixing, mark it OPEN with a reason, so the")
        print("decision is written down rather than lost in a red number.")
    if closed:
        print("\nA NEWLY CLOSED entry is good news that must not stay OPEN:")
        print("move it to hooks/cases.py so it cannot reopen unnoticed.")
    return 1 if (leaked or over or closed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
