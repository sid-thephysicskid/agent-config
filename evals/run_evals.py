#!/usr/bin/env python3
"""Run every check that can run without an agent, then print a scorecard.

    python3 evals/run_evals.py
    python3 evals/run_evals.py --json > evals/results/static-$(date +%F).json
    python3 evals/run_evals.py --severity error

Exit status is 1 if any error-severity finding was produced, so this is usable
as a CI gate. Warn and info do not fail the run.

What this does NOT do: run a skill. Judging whether /diagnose actually builds a
feedback loop before hypothesising requires a fresh agent session, and this
process cannot spawn one. That measurement is not
attempted here rather than approximated, and evals/README.md says what a real
one would need. Everything printed below is measured from the files on disk.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.harness import guard_checks, static_checks  # noqa: E402
from evals.harness.model import Finding, load_skills  # noqa: E402

SEV_ORDER = {"error": 0, "warn": 1, "info": 2}


def collect() -> Dict[str, object]:
    skills = load_skills()
    operator_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "operator-skills")
    if os.path.isdir(operator_dir):
        skills.extend(load_skills(operator_dir))
    findings = []  # type: List[Finding]

    for check in static_checks.ALL_CHECKS:
        findings.extend(check(skills))

    fixtures = guard_checks.Fixtures()
    fixtures.build()
    # Recorded, not inferred. The summary used to describe what it WOULD have
    # measured, so a machine with no git printed a healthy-looking report.
    guard_ran = not fixtures.error
    try:
        findings.extend(guard_checks.check_prescribed_commands(skills, fixtures))
        claims = guard_checks.load_claims()
        findings.extend(guard_checks.check_guard_claims(fixtures, claims))
    finally:
        fixtures.cleanup()


    return {
        "skills": skills,
        "findings": findings,
        "coverage": guard_checks.command_coverage(skills),
        "claims": claims,
        "guard_ran": guard_ran,
    }


def print_findings(findings: List[Finding], min_severity: str) -> None:
    threshold = SEV_ORDER[min_severity]
    by_check = defaultdict(list)  # type: Dict[str, List[Finding]]
    for f in findings:
        if SEV_ORDER[f.severity] <= threshold:
            by_check[f.check].append(f)
    for check in sorted(by_check):
        items = sorted(by_check[check], key=lambda f: (SEV_ORDER[f.severity], f.skill or ""))
        print("\n== %s (%d) ==" % (check, len(items)))
        for f in items:
            tag = f.severity.upper()
            if f.basis == "heuristic":
                tag += "*"
            print("  [%-6s] %-11s %s" % (tag, f.skill or "-", f.message))
            if f.evidence:
                print("             %s" % f.evidence[:150])


def print_scorecard(data: Dict[str, object]) -> None:
    """One row per skill: how big it is, how much of it the guard saw, verdict.

    The out/in/dup columns are gone with the checks that produced them. They
    counted references between skills and repeated phrases, neither of which
    ever decided anything, and a column nobody acts on is a column that teaches
    you to skim the table.
    """
    skills = data["skills"]
    findings = data["findings"]  # type: List[Finding]
    coverage = data["coverage"]

    counts = defaultdict(lambda: defaultdict(int))  # type: Dict[str, Dict[str, int]]
    for f in findings:
        if f.skill:
            counts[f.skill][f.severity] += 1

    total_words = sum(s.word_count for s in skills) or 1
    header = "%-11s %6s %6s %5s %4s %4s  %s" % (
        "skill", "words", "share", "cmds", "err", "warn", "status")
    print("\n" + header)
    print("-" * len(header))
    for s in sorted(skills, key=lambda s: -s.word_count):
        err = counts[s.name]["error"]
        warn = counts[s.name]["warn"]
        print("%-11s %6d %5.1f%% %5d %4d %4d  %s"
              % (s.name + ("*" if s.vendored else ""),
                 s.word_count,
                 100.0 * s.word_count / total_words,
                 coverage.get(s.name, (0, 0))[0],
                 err, warn,
                 "FAIL" if err else ("WARN" if warn else "ok")))
    print("-" * len(header))
    print("%-11s %6d %5.1f%%" % ("total", total_words, 100.0))
    print("* vendored skill (this repo does not author it) or heuristic threshold")
    print("cmds = fenced command lines from this skill run past the live guard")

def print_limits(data: Dict[str, object]) -> None:
    skills = data["skills"]
    coverage = data["coverage"]
    checked = sum(v[0] for v in coverage.values())
    skipped = sum(v[1] for v in coverage.values())
    claims = data["claims"]

    print("\n== what this run measured, and what it did not ==")
    # Reported from what RAN, not from re-parsing the inputs. These two lines
    # used to be derived from the markdown and from the length of the claims
    # file, so a run whose git fixtures never built printed the same numbers as
    # a healthy one and exited 0. The counts described what it would have done.
    if data.get("guard_ran"):
        print("  measured: %d skills, %d fenced command lines run past the live guard" % (len(skills), checked))
        print("            (%d further fenced lines were not commands and were skipped)" % skipped)
        print("  measured: %d stated guard behaviours, each pinned to the sentence that claims it" % len(claims))
    else:
        print("  measured: %d skills, and NO command reached the live guard" % len(skills))
        print("  NOT measured: every guard behaviour. The fixtures did not build,")
        print("                so nothing was run past the guard and no claim was")
        print("                checked. See the errors above.")
    print("  measured: frontmatter, house style, links, and referenced paths")
    print("  NOT measured: whether any skill improves an agent's output. That needs a")
    print("                fresh agent per task, with and without. See evals/README.md.")
    print("  NOT measured: guard behaviour under states the fixtures do not reproduce,")
    print("                for example detached HEAD, a linked worktree, or a dirty index.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit findings as JSON instead of text")
    ap.add_argument(
        "--severity",
        choices=("error", "warn", "info"),
        default="info",
        help="lowest severity to print (default info)",
    )
    args = ap.parse_args()

    data = collect()
    findings = data["findings"]  # type: List[Finding]

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [
                        {
                            "check": f.check,
                            "severity": f.severity,
                            "skill": f.skill,
                            "message": f.message,
                            "evidence": f.evidence,
                            "basis": f.basis,
                        }
                        for f in findings
                    ],
                    "scorecard": {
                        s.name: {
                            "words": s.word_count,
                            "vendored": s.vendored,
                            "commands_checked": data["coverage"].get(s.name, (0, 0))[0],
                        }
                        for s in data["skills"]
                    },
                },
                indent=2,
            )
        )
    else:
        print_findings(findings, args.severity)
        print_scorecard(data)
        print_limits(data)
        totals = defaultdict(int)  # type: Dict[str, int]
        for f in findings:
            totals[f.severity] += 1
        print(
            "\ntotals: %d error, %d warn, %d info"
            % (totals["error"], totals["warn"], totals["info"])
        )

    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
