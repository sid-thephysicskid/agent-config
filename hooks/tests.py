#!/usr/bin/env python3
"""Regression tests for guard_rules.

Run: python3 hooks/tests.py

Every BLOCK case here is a bypass that was found by an adversarial audit and
must never regress. Every ALLOW case is a legitimate command that was once
wrongly blocked, or that must stay fast and unblocked. A guard that cries wolf
gets switched off, so the ALLOW list matters as much as the BLOCK list.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_parse  # noqa: E402
import guard_rules  # noqa: E402
from cases import CMD_CASES, PATH_CASES  # noqa: E402
from fixtures import FEAT, MAIN  # noqa: E402


ADAPTER_COUNT = 5


# Rule tables whose rows are (pattern, reason, fix). The reason is already a
# unique string per row, so it doubles as the row's identity and no fourth
# element is needed.
REASON_TABLES = ("DESTRUCTIVE_GIT", "DESTRUCTIVE_TOOLS", "PRODUCTION_DEPLOYS")


def test_every_rule_row_fires_for_some_case():
    """Every row of the three big tables must be the reason SOME case blocked.

    43 rows had nothing pinning them. That is not theoretical: `yarn publish`
    was a live rule with no case, because a sibling row caught the one command
    in the corpus that touched it, so the row could be deleted with the suite
    green and the hole would have opened silently.

    Reachability by REASON rather than by a name field: a row's reason is
    already unique, so it identifies the row without a fourth tuple element and
    without 43 edits. A duplicated reason fails here too, which is correct, a
    block message that cannot tell you which rule fired is worth fixing anyway.

    Weaker than tests/mutate.py, which proves a row changes a verdict. That one
    takes four minutes, so it stays manual and this stands guard in between.
    """
    seen = set()
    for case in CMD_CASES:
        hit = guard_rules.check_command(case[0], case[1])
        if hit:
            seen.add(hit[0])
    bad = []
    for label in REASON_TABLES:
        # Through the facade, which re-exports every rule module's tables.
        reasons = [r[1] for r in getattr(guard_rules, label)]
        for reason in reasons:
            if reasons.count(reason) > 1:
                bad.append(f"{label}: two rows share the reason {reason!r}")
            # Prefix, not equality: check_deploy appends "…which skips CI,
            # review and branch protection" to the row's own text, so the
            # reason the user sees is longer than the reason in the table.
            elif not any(s.startswith(reason) for s in seen):
                bad.append(f"{label}: no case blocks with {reason!r}")
    return sorted(set(bad))


def test_every_db_wipe_rule_is_reachable():
    """Every row of DB_WIPE_RULES must fire for at least one command.

    This is the assertion a boolean suite cannot make. `redis-cli FLUSHALL`
    blocking proves *something* blocked it; it does not prove the redis rule
    exists, because a broader rule could be catching it. Deleting a row and
    watching the suite stay green is exactly the failure the ~46% mutation
    score was measuring, and naming the rules is what makes it testable.

    A row with no command that reaches it is a dead row, and a dead row is a
    hole nobody notices.
    """
    probes = (
        "mongosh --eval 'db.dropDatabase()'",
        "mongosh --eval 'db.users.drop()'",
        "mongo --eval 'db.events.deleteMany({})'",
        "redis-cli FLUSHALL",
        "rails db:drop",
        "php artisan migrate:fresh",
    )
    fired = set()
    for cmd in probes:
        rule = guard_rules.db_wipe_rule_for(cmd)
        if rule:
            fired.add(rule.name)
    missing = [r.name for r in guard_rules.DB_WIPE_RULES if r.name not in fired]
    return missing


def test_oversize_middle_agrees_with_the_rules():
    """A blocked command stays blocked when padded past the analysis window.

    Only a head and a tail of a very long command are parsed, so the discarded
    middle gets a cheap signal scan instead. That list used to live in the
    parser, hand-copied from the rules, and it went stale: sixteen classes
    including every irreversible publish were allowed once buried, with both
    suites green.

    The assertion is agreement, not blocking. A class the rules do not block
    must not block when buried either, which is what caught the parser
    inventing mkfs and `dd of=/dev/` that no rule ever had.
    """
    pad = ("echo " + "a" * 60 + "\n") * 520          # past MAX_ANALYSED
    tail = ("echo " + "a" * 60 + "\n") * 140         # past TAIL_ANALYSED
    bad = []
    for cmd in OVERSIZE_PROBES:
        alone = bool(guard_rules.check_command(cmd, MAIN))
        buried = bool(guard_rules.check_command(pad + cmd + "\n" + tail, MAIN))
        if alone != buried:
            bad.append(f"{cmd!r}: alone={'BLOCK' if alone else 'ALLOW'}, "
                       f"buried={'BLOCK' if buried else 'ALLOW'}")
    return bad


# Module level so the suite can count them. Hand-listed, which is itself a
# known weakness: a rule added without a probe here passes silently.
OVERSIZE_PROBES = (
        "git push --force origin main", "git reset --hard HEAD~1",
        "git clean -fd", "git branch -D feature/x", "git filter-branch --all",
        "git reflog expire --expire=now --all",
        "git update-ref -d refs/heads/main",
        "psql app -c 'DROP TABLE users'", "psql app -c 'DELETE FROM users'",
        "npx prisma migrate reset", "supabase db reset",
        "redis-cli -h db.example.com FLUSHALL", "rails db:drop",
        "php artisan migrate:fresh", "terraform destroy -auto-approve",
        "kubectl delete namespace prod", "gh repo delete acme/app --yes",
        "gh api -X DELETE /repos/acme/app", "gh pr merge 1 --admin",
        "dropdb production", "vercel rm my-project --yes",
        "aws s3 rm s3://bucket --recursive", "npm publish", "cargo publish",
        "twine upload dist/x.whl", "gem push x.gem", "poetry publish",
        "rm -rf /",
        "mkfs.ext4 /dev/sda1", "dd if=/dev/zero of=/dev/sda",
        # Production deploys, both shapes, plus the previews that must not move.
        "vercel --prod", "fly deploy", "wrangler deploy", "modal deploy app.py",
        "npx prisma migrate deploy",
        "vercel", "vercel ls", "wrangler dev", "npx prisma migrate dev",
        # ...and the ordinary dd, which writes a file and must stay allowed
        # both alone and buried.
        "dd if=/dev/zero of=testfile bs=1M count=100",
        # ...and ordinary prose, which must not trip a signal either way.
        "echo 'the release notes mention a deleted table'",
)


def test_every_runner_is_reachable_by_every_shape():
    """Every name in RUNNER_NAMES must block in both shapes that execute.

    Five hand-copied runner lists used to exist. They drifted, and each gap was
    a sibling spelling of an already-blocked command being allowed: `bun -c`,
    `| ash`, `| busybox sh`, `| python2`. Individual cases in cases.py pin the
    four that were found. This pins the PROPERTY, so a runner added to the set
    without being wired into every matcher fails here rather than waiting for
    someone to think of its case.

    Piping into a runner and handing it `-c` are the two shapes every entry
    supports, so they are the two asserted.
    """
    bad = []
    for name in sorted(guard_parse.RUNNER_NAMES):
        if not guard_rules.check_command("echo 'rm -rf ~' | " + name, "/tmp"):
            bad.append(f"| {name}")
        if not guard_rules.check_command(name + " -c 'rm -rf /'", "/tmp"):
            bad.append(f"{name} -c")
    return bad


def test_segment_rules_are_named():
    """Each SEGMENT_RULES entry must be the one credited for its own block.

    Pins rule IDENTITY rather than outcome, which is the whole point of the
    registry. Without this, the `sql` rule could be deleted and `prod-db`
    would still block half its cases, leaving the suite green.
    """
    want = (
        ("psql -c 'DROP TABLE users'", "sql"),
        ("psql -h db.production.internal -U admin app", "prod-db"),
        ("redis-cli FLUSHALL", "db-wipe"),
        ("rm -rf /", "rm"),
        ("terraform destroy -auto-approve", "tools"),
        ("python3 -c \"import shutil;shutil.rmtree('/')\"", "inline-code"),
    )
    wrong = []
    for cmd, expected in want:
        hit = guard_rules.check_command(cmd, FEAT)
        got = guard_rules.last_rule()
        if not hit:
            wrong.append(f"{cmd!r} did not block at all")
        elif got != expected:
            wrong.append(f"{cmd!r} was credited to {got!r}, wanted {expected!r}")
    return wrong


def test_git_call_budget():
    """Subprocess COUNT, not wall clock.

    The substitution recursion re-enters check_command, which used to clear
    every cache and reset MAX_GIT_CALLS on entry, so each `$(...)` on the line
    handed the outer scan a fresh budget: 1000 of them meant 2000 git
    subprocesses and 11.5s against a 5 second hook timeout, and a timeout fails
    open. A count is the right assertion because it does not flake under load,
    which is what made the timing budgets untrustworthy as an oracle.
    """
    # Count REAL subprocess launches, not the module's own counter: the bug
    # this pins is the counter being reset mid-scan, so reading it afterwards
    # reports whatever the last reset left behind.
    fails = []
    real_run = guard_rules.subprocess.run
    seen = [0]

    def counting_run(*a, **kw):
        seen[0] += 1
        return real_run(*a, **kw)

    for label, cmd in (
            ('substitution recursion', 'git log "$(:)";' * 1000),
            ('distinct -C targets', ";".join("git -C d%d log" % i for i in range(1500))),
            ('backtick spelling', 'git status "`:`";' * 800)):
        seen[0] = 0
        guard_rules.subprocess.run = counting_run
        try:
            guard_rules.check_command(cmd, MAIN)
        finally:
            guard_rules.subprocess.run = real_run
        # Some slack over the cap: a few helpers legitimately run outside it.
        if seen[0] > guard_rules.MAX_GIT_CALLS * 2:
            fails.append(f"  {label}: {seen[0]} subprocesses launched, cap is "
                         f"{guard_rules.MAX_GIT_CALLS}")
    return fails


def test_adapters():
    """Adapter-level payload shapes. The rules module can be correct while an
    adapter silently fails open on a shape it does not recognise."""
    import json as _json
    here = os.path.dirname(os.path.abspath(__file__))
    out = []

    def run(hook, payload):
        r = subprocess.run(["python3", os.path.join(here, hook)],
                           input=_json.dumps(payload), capture_output=True, text=True)
        return r.returncode == 2

    if not run("guard-bash.py", {"tool_name": "Bash",
               "tool_input": {"command": ["rm", "-rf", "/"]}, "cwd": MAIN}):
        out.append("  guard-bash: list-form command not blocked")
    if not run("guard-codex.py", {"tool_name": "shell",
               "tool_input": {"command": "rm -rf /"}, "cwd": MAIN}):
        out.append("  guard-codex: shell tool not blocked")
    if not run("guard-codex.py", {"tool_name": "read",
               "tool_input": {"path": ["/app/.env"]}}):
        out.append("  guard-codex: list-form path not blocked")
    if not run("guard-files.py", {"tool_name": "Read",
               "tool_input": {"file_path": ["/app/.env"]}}):
        out.append("  guard-files: list-form file_path not blocked")
    if run("guard-bash.py", {"tool_name": "Bash", "tool_input": {}, "cwd": MAIN}):
        out.append("  guard-bash: empty tool_input should fail open, not block")
    return out




def _worst(shapes):
    """Seconds taken by the slowest of these commands.

    A tuple, not one string: the database budget needs twelve shapes, and the
    others are the same measurement with one.
    """
    import time
    worst = 0.0
    for cmd in shapes:
        start = time.time()
        guard_rules.check_command(cmd, MAIN)
        worst = max(worst, time.time() - start)
    return worst


# label, budget in seconds, () -> shapes, and the incident it pins.
#
# Every row is a fail-open DoS that shipped: the hook is killed at five seconds
# and the host reads the kill as "allowed", so slow input was a generic
# disable-the-guard primitive. The shapes are built by a lambda because several
# are 40KB, and building them at import would cost --no-perf runs too.
PERF_BUDGETS = (
    ("ReDoS: 20k-token command", 2.0,
     lambda: ("cat " + "api." * 20000 + "z",),
     "KEYISH was quadratic and blew the 5s hook timeout"),

    ("1600 config flags", 2.0,
     lambda: ("kubectl " + "--kubeconfig /tmp/a " * 1600 + "get pods",),
     "the config-flag loop re-tokenised the whole segment per match: 26s"),

    ("1000 git pushes in one segment", 2.0,
     lambda: ("git push " * 1000,),
     "the refspec searches ran once per git invocation, each backtracking "
     "over the whole segment: 15.5s"),

    ("270KB heredoc", 2.0,
     lambda: ("cat > big.py <<'EOF'\n" + "x = 1\n" * (270 * 1024 // 6) + "\nEOF",),
     "a large heredoc is a file write, not an instruction; re-scanning the "
     "whole command per segment made it take 163s"),

    ("1600 small heredocs", 2.0,
     lambda: ("cat > /tmp/x.sh <<E\nb\nE\n" * 1600,),
     "MANY small heredocs, not one big one: the rejoin ran six regexes per "
     "opener, quadratic, 12.5s at 37KB. The big-write shape cannot see it"),

    ("32KB of brace tokens", 2.0,
     lambda: (("git {a,b,c,d}{e,f,g,h}{i,j,k,l}{m,n,o,p};" * 798) + " rm -rf ~",),
     "brace_expand runs per braced token per segment, so cost is members x "
     "tokens x segments: 7.5s under MAX_ANALYSED, so nothing truncated"),

    ("8000 pipes", 2.0,
     lambda: (" | ".join(["echo x"] * 8000),),
     "shell_fed_segments scanned forward per piped segment and only stopped "
     "at a segment not followed by a pipe; a pipe chain has none, so it hung"),

    ("1500 git tokens", 2.0,
     lambda: ("echo " + " ".join(["git"] * 1500) + " && rm -rf ~/",),
     "git_invocations shelled out once per `git` token per segment: 8s"),

    ("database clients, worst of twelve shapes", 2.0,
     lambda: (
         "psql " + "-h localhost " * 1000 + "-c 'DROP TABLE t'",
         "psql " + "-h prod-db.example.com " * 1000 + "-c 'DROP TABLE t'",
         "psql " + "postgres://u@localhost/a " * 500 + "-c 'DROP TABLE t'",
         "sqlite3 dev.db " + "x " * 4000 + "'DROP TABLE t'",
         "sqlite3 " + "a" * 40000 + ".db 'DROP TABLE t'",
         "mongosh --eval '" + "x" * 40000 + "db.dropDatabase()'",
         "redis-cli " + "k" * 40000 + " FLUSHALL",
         "rails " + "x" * 40000 + " db:drop",
         "psql " + "$PROD_URL " * 4000,
         " ; ".join(["mongosh --eval 'db.x.find()'"] * 2000),
         " ; ".join(["psql -h localhost -c 'select 1'"] * 2000),
         "cat " + "~/.ssh/config " * 2000,
     ),
     "five fail-open DoS bugs so far, each quadratic work on a shape the "
     "suite had no big instance of; is_local_db, the four client scans and "
     "the $VAR walk all run per segment"),
)

# One per budget, plus the correctness assertion below that the trailing
# command in the git-token shape still blocked. Derived, never typed: it was
# hardcoded to 8 while ten things could fail.
PERF_ASSERTIONS = len(PERF_BUDGETS) + 1


def main():
    # --no-perf runs correctness only. The wall-clock budgets below flake on a
    # loaded machine, and install.sh gates on this suite: an aborted install
    # whose suggested command then prints PASS is a dead end for the adopter.
    # It also matters for mutation testing: counting a timing flake as a "kill"
    # made the guard's apparent mutation score roughly twice its real one.
    perf = "--no-perf" not in sys.argv
    fails = []
    for case in CMD_CASES:
        # A fourth element pins WHICH rule fired, as a substring of the reason.
        # Booleans alone hid every rule whose only coverage was a command some
        # second, unrelated rule also blocked: a mutation pass found the short
        # `-f` force-push spelling deletable with the suite still green,
        # because on a protected branch the branch rule caught it anyway.
        cmd, cwd, should = case[0], case[1], case[2]
        want_reason = case[3] if len(case) > 3 else None
        hit = guard_rules.check_command(cmd, cwd)
        got = hit is not None
        if got != should:
            fails.append(f"  {'should BLOCK' if should else 'should ALLOW'}: {cmd}")
        elif want_reason and want_reason.lower() not in hit[0].lower():
            fails.append(f"  blocked for the WRONG reason: {cmd}\n"
                         f"      wanted {want_reason!r} in {hit[0]!r}")
        # Same command, argv-shaped. A host may hand over ["bash","-lc",cmd]
        # instead of a string, and the two must agree or one host runs weaker
        # rules than the other on the same input. floor.py asserted this over
        # its own 375 cases; 66 of the 1211 here disagreed, including an inline
        # program deleting a system path and a pipe into a shell.
        if isinstance(cmd, str):
            argv = guard_rules.check_command(["bash", "-lc", cmd], cwd)
            if (argv is not None) != got:
                fails.append(f"  argv form disagrees with the string form: {cmd}\n"
                             f"      string={'BLOCK' if got else 'allow'} "
                             f"argv={'BLOCK' if argv else 'allow'}")
    for path, writing, should in PATH_CASES:
        got = guard_rules.check_path(path, writing) is not None
        if got != should:
            fails.append(f"  {'should BLOCK' if should else 'should ALLOW'}: path {path}")

    fails += test_adapters()
    fails += test_git_call_budget()
    for name in test_every_db_wipe_rule_is_reachable():
        fails.append(f"  DB_WIPE_RULES row {name!r} is unreachable: no command fires it")
    for problem in test_every_rule_row_fires_for_some_case():
        fails.append(f"  unpinned rule row: {problem}")
    for problem in test_segment_rules_are_named():
        fails.append(f"  rule identity: {problem}")
    for shape in test_every_runner_is_reachable_by_every_shape():
        fails.append(f"  runner {shape!r} is in RUNNER_NAMES but does not block")
    for disagreement in test_oversize_middle_agrees_with_the_rules():
        fails.append(f"  oversize middle disagrees with the rules: {disagreement}")
    if perf:
        for label, budget, shapes, _why in PERF_BUDGETS:
            elapsed = _worst(shapes())
            if elapsed > budget:
                fails.append(f"  {label} took {elapsed:.1f}s "
                             f"(budget {budget}s, hook timeout is 5s)")
        # Not a budget: the padded shape must still BLOCK. A fast wrong answer
        # is the failure this whole section exists to prevent.
        if guard_rules.check_command(
                "echo " + " ".join(["git"] * 1500) + " && rm -rf ~/", MAIN) is None:
            fails.append("  1500 git tokens: trailing rm -rf ~/ was not blocked")

    # The identity assertions count too: one per DB_WIPE_RULES row and one per
    # named SEGMENT_RULES probe. They are the only checks here that pin WHICH
    # rule fired rather than whether something did.
    #
    # Derived, never typed. The perf term was hardcoded to 8 while ten perf
    # assertions could fail, and the two reachability tests contributed
    # failures without contributing to the total, so `PASS n/n` was a number
    # this suite had made up. A suite that miscounts itself has no business
    # grading anything else.
    total = (len(CMD_CASES) + len(PATH_CASES) + ADAPTER_COUNT
             + len(guard_rules.DB_WIPE_RULES) + len(guard_rules.SEGMENT_RULES)
             + 2 * len(guard_parse.RUNNER_NAMES) + len(OVERSIZE_PROBES)
             + (PERF_ASSERTIONS if perf else 0))
    if fails:
        print(f"FAIL {len(fails)}/{total}")
        print("\n".join(fails))
        return 1
    print(f"PASS {total}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
