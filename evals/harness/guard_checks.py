"""Checks that run skill-prescribed commands past the repo's own guard.

Nothing here executes a candidate command. Every command is passed to
`hooks/guard_rules.check_command(cmd, cwd)` as a string, which is a pure
decision function: it parses the command and consults the git state of `cwd`.
The guard is live on the machine this repo installs onto, so actually running
these strings through a shell would be both destructive and blocked.

Three fixtures are built with `git init` in a temp directory, because most of
the interesting rules are branch-conditional and one of them is conditional on
the repo having no history at all:

    protected  on `main`, one commit
    feature    on `fix/eval-fixture`, one commit
    virgin     on `main`, no commits (what /bootstrap's first commit sees)

The fixtures are throwaway and are removed at the end.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

from .model import EVALS_DIR, REPO_ROOT, Finding, SkillDoc, iter_fences, read

HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")

# Commands we recognise as commands. A fenced block line whose first word is
# not in here is skipped, and the number skipped is reported, so coverage is
# visible rather than implied.
KNOWN_COMMANDS = set(
    """
git gh npm npx node python python3 pip pip-audit cargo ln ls cat rm mv cp mkdir
printf echo grep sed awk xargs find chmod curl wget psql mysql mongo docker make
just vercel heroku netlify fly set test sleep tee sort uniq wc head tail diff
pytest jest vitest eslint prettier tsc ruff mypy black touch export source
""".split()
)

ASSIGN_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=\$?\(?")
SPLIT_RE = re.compile(r"&&|\|\||;|\|")


def _load_guard():
    if HOOKS_DIR not in sys.path:
        sys.path.insert(0, HOOKS_DIR)
    import guard_rules  # noqa: E402

    return guard_rules


FIXTURE_SPECS = (
    ("protected", "main", True),
    ("feature", "fix/eval-fixture", True),
    ("virgin", "main", False),
)


class Fixtures(object):
    """Throwaway git repos standing in for the states the skills run in."""

    def __init__(self) -> None:
        self.dirs = {}  # type: Dict[str, str]
        self.error = None  # type: Optional[str]

    def build(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": "eval",
                "GIT_AUTHOR_EMAIL": "eval@example.invalid",
                "GIT_COMMITTER_NAME": "eval",
                "GIT_COMMITTER_EMAIL": "eval@example.invalid",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
            }
        )
        for label, branch, with_commit in FIXTURE_SPECS:
            try:
                d = tempfile.mkdtemp(prefix="skill-eval-")
                subprocess.run(
                    ["git", "init", "-q", "-b", branch, d],
                    check=True,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                if with_commit:
                    with open(os.path.join(d, "placeholder.txt"), "w") as fh:
                        fh.write("fixture\n")
                    subprocess.run(["git", "-C", d, "add", "placeholder.txt"], check=True, env=env)
                    subprocess.run(
                        ["git", "-C", d, "commit", "-q", "-m", "fixture"],
                        check=True,
                        env=env,
                        stdout=subprocess.DEVNULL,
                    )
                self.dirs[label] = d
            except (OSError, subprocess.CalledProcessError) as exc:
                self.error = str(exc)
                return

    def cleanup(self) -> None:
        for d in self.dirs.values():
            shutil.rmtree(d, ignore_errors=True)


def extract_commands(skill: SkillDoc) -> Tuple[List[Tuple[int, str]], int]:
    """Pull candidate shell command lines out of fenced blocks.

    Returns (commands, skipped_line_count). A line counts as a command when
    the first word of one of its `&&`/`||`/`;`/`|` segments, with any leading
    `VAR=` or `$(` stripped, is in KNOWN_COMMANDS. Continuations ending in a
    backslash are joined first.

    What this misses, on purpose: commands quoted inline in prose, including
    the ones a skill tells you *not* to run. Those are covered by the claims
    file instead, where the expected verdict can be stated.
    """
    commands = []  # type: List[Tuple[int, str]]
    skipped = 0
    for fence in iter_fences(read(skill.skill_md)):
        joined = []  # type: List[Tuple[int, str]]
        buf = ""
        buf_line = 0
        for offset, raw in enumerate(fence.lines):
            line = raw.rstrip()
            if not buf:
                buf_line = fence.start_line + offset + 1
            if line.endswith("\\"):
                buf += line[:-1] + " "
                continue
            buf += line
            joined.append((buf_line, buf))
            buf = ""
        if buf:
            joined.append((buf_line, buf))

        for lineno, line in joined:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            is_cmd = False
            for seg in SPLIT_RE.split(stripped):
                seg = seg.strip()
                seg = ASSIGN_RE.sub("", seg)
                seg = seg.lstrip("(&$ \t")
                first = seg.split()[0] if seg.split() else ""
                if first in KNOWN_COMMANDS:
                    is_cmd = True
                    break
            if is_cmd:
                commands.append((lineno, stripped))
            else:
                skipped += 1
    return commands, skipped


def check_prescribed_commands(skills: Sequence[SkillDoc], fixtures: Fixtures) -> List[Finding]:
    """Every command a skill tells the agent to run should survive the guard.

    Evaluated on the feature-branch fixture, because that is where the suite
    says the work happens: /ship step 1, /diagnose phase 5 and /prototype all
    branch before they run anything. A command blocked here is a skill telling
    an agent to do something this machine will refuse, which is a dead end
    mid-pipeline.

    Limitation worth stating: placeholders are passed through as written
    (`<path>`, `$BRANCH`), so this measures the shape of the command, not the
    expanded one.
    """
    if fixtures.error:
        return [
            Finding(
                "guard-prescribed",
                # ERROR, not warn. A warn does not fail the run, so a
                # machine with no git reported success while verifying
                # nothing, and the summary printed the counts it had
                # not measured. A harness that cannot run is not a pass.
                "error",
                "could not build git fixtures, guard checks did not run: %s" % fixtures.error,
            )
        ]
    guard = _load_guard()
    cwd = fixtures.dirs["feature"]
    out = []  # type: List[Finding]
    for s in skills:
        commands, _skipped = extract_commands(s)
        for lineno, cmd in commands:
            verdict = guard.check_command(cmd, cwd)
            if verdict is not None:
                out.append(
                    Finding(
                        "guard-prescribed",
                        "error",
                        "SKILL.md line %d prescribes a command the guard blocks" % lineno,
                        s.name,
                        evidence="%s || %s" % (cmd[:110], verdict[0][:80]),
                    )
                )
    return out


def command_coverage(skills: Sequence[SkillDoc]) -> Dict[str, Tuple[int, int]]:
    """Per skill: (commands checked, fenced lines skipped as non-commands)."""
    return {s.name: (lambda t: (len(t[0]), t[1]))(extract_commands(s)) for s in skills}


def load_claims(path: Optional[str] = None) -> List[dict]:
    path = path or os.path.join(EVALS_DIR, "guard_claims.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["claims"]


def check_guard_claims(fixtures: Fixtures, claims: Optional[List[dict]] = None) -> List[Finding]:
    """Verify the statements the skills make about what the guard does.

    Several skills assert guard behaviour as fact ("the guard blocks the
    commit", "the guard allows this from the base branch"). Those assertions
    are load-bearing: an agent that believes a wrong one either walks into a
    block it was told would not happen, or skips a safe path it was told was
    unsafe. Each claim carries the exact sentence it came from, and the check
    fails if that sentence is no longer in the file, so the claims cannot rot
    silently while still reporting green.
    """
    if fixtures.error:
        return [
            Finding(
                "guard-claims",
                # ERROR, not warn. A warn does not fail the run, so a
                # machine with no git reported success while verifying
                # nothing, and the summary printed the counts it had
                # not measured. A harness that cannot run is not a pass.
                "error",
                "could not build git fixtures, claim checks did not run: %s" % fixtures.error,
            )
        ]
    guard = _load_guard()
    claims = claims if claims is not None else load_claims()
    out = []  # type: List[Finding]
    for claim in claims:
        skill = claim["skill"]
        source = os.path.join(REPO_ROOT, claim["file"])
        if not os.path.exists(source):
            out.append(
                Finding("guard-claims", "error", "claim %s cites a missing file %s" % (claim["id"], claim["file"]), skill)
            )
            continue
        if claim.get("quote") and claim["quote"] not in read(source):
            out.append(
                Finding(
                    "guard-claims",
                    "error",
                    "claim %s quotes text that is no longer in %s; the claim data is stale"
                    % (claim["id"], claim["file"]),
                    skill,
                    evidence=claim["quote"][:120],
                )
            )
            continue
        cwd = fixtures.dirs[claim["branch"]]
        verdict = guard.check_command(claim["command"], cwd)
        actual = "block" if verdict is not None else "allow"
        if actual != claim["expect"]:
            out.append(
                Finding(
                    "guard-claims",
                    "error",
                    "claim %s says the guard would %s %r on a %s branch; it %ss it"
                    % (claim["id"], claim["expect"], claim["command"], claim["branch"], actual),
                    skill,
                    evidence=claim.get("why", ""),
                )
            )
        elif claim.get("kind") == "prose-only-rule":
            out.append(
                Finding(
                    "guard-claims",
                    "info",
                    "%r is forbidden by prose only; the guard allows it, so nothing catches it"
                    % claim["command"],
                    skill,
                    evidence=claim.get("why", ""),
                )
            )
        elif claim.get("kind") == "misleading-prose":
            out.append(
                Finding(
                    "guard-claims",
                    "warn",
                    "guard behaviour matches, but the sentence describing it reads the other way",
                    skill,
                    evidence=claim.get("why", ""),
                )
            )
        elif claim.get("kind") == "already-enforced":
            out.append(
                Finding(
                    "guard-claims",
                    "info",
                    "%r is spelled out in prose and also blocked by the guard" % claim["command"],
                    skill,
                    evidence=claim.get("why", ""),
                )
            )
    return out
