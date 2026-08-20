#!/usr/bin/env python3
"""Pre-publish audit. Fails the build on anything that must never ship.

Run: python3 tests/audit.py

This is the gate that stops a credential, a personal detail, or a false
licence claim reaching a public clone. It runs in CI on every change, because
the one time it matters is the time nobody thought to run it by hand.

BLOCKER fails the build. REVIEW and NOTE are printed and do not.
"""
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a],
                          capture_output=True, text=True).stdout


def has_git_checkout():
    result = subprocess.run(["git", "-C", REPO, "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "true"


def files_on_disk():
    found = []
    for current, dirs, names in os.walk(REPO):
        dirs[:] = [name for name in dirs
                   if name not in (".git", "__pycache__", "node_modules")]
        for name in names:
            path = os.path.join(current, name)
            if os.path.isfile(path) and not os.path.islink(path):
                found.append(os.path.relpath(path, REPO))
    return sorted(found)


HAS_GIT = has_git_checkout()
if HAS_GIT:
    TRACKED = [f for f in git("ls-files", "--cached", "--others",
                               "--exclude-standard").split("\n")
               if f and os.path.isfile(os.path.join(REPO, f))]
else:
    # A history-free public export has no .git directory. Audit every regular
    # file in that tree instead of silently treating the export as empty.
    TRACKED = files_on_disk()
findings = defaultdict(list)


def add(sev, what, detail=""):
    findings[sev].append((what, detail))


def read(f):
    return open(os.path.join(REPO, f), encoding="utf-8", errors="ignore").read()


# ---- credentials -----------------------------------------------------------
# Shapes, not entropy heuristics: a false positive here blocks a merge, so each
# pattern names a specific issuer format.
SECRETS = [
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic key"),
    # `sk-[A-Za-z0-9]{32,}` alone missed every CURRENT issuer format, because
    # the segment after `sk-` breaks on the first hyphen or underscore:
    # sk-proj- is OpenAI's default today, and sk_live_ is Stripe. The pattern
    # right above this one already showed that keys carry separators.
    (r"sk-proj-[A-Za-z0-9_-]{20,}", "OpenAI project key"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI-style key"),
    (r"sk_(live|test)_[A-Za-z0-9]{20,}", "Stripe secret key"),
    (r"rk_(live|test)_[A-Za-z0-9]{20,}", "Stripe restricted key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    # The id was matched and the SECRET never was, so the half that actually
    # grants access could be committed while the gate reported clean. Anchored
    # on an assignment, because 40 base64 characters on their own are not a
    # distinctive enough shape to refuse a merge over.
    (r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}", "AWS secret access key"),
    (r"AIza[0-9A-Za-z_-]{35}", "Google API key"),
    (r"ya29\.[0-9A-Za-z_-]{20,}", "Google OAuth token"),
    (r"npm_[A-Za-z0-9]{36}", "npm token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"xapp-[0-9]-[A-Za-z0-9-]{10,}", "Slack app token"),
    (r"glpat-[A-Za-z0-9_-]{20,}", "GitLab token"),
    (r"dop_v1_[a-f0-9]{64}", "DigitalOcean token"),
    (r"hf_[A-Za-z0-9]{30,}", "Hugging Face token"),
    # Any client, not just one. postgres was matched and mysql, mongodb and
    # redis were not, though the compliance fixtures use exactly those shapes.
    (r"(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp|clickhouse)://"
     r"[^\s'\"/]*:[^\s'\"@/]{6,}@", "database URL with a password"),
]
# Files whose entire purpose is to LOOK like a credential, listed one by one
# rather than by pattern. The compliance harness needs a fixture holding a
# convincing database URL, because a task that tempts an agent into committing
# a secret cannot use an obviously fake one.
#
# Named explicitly, and deliberately NOT solved with a marker line inside the
# fixture: the agent under test reads that file during a run, and a comment
# saying TEST FIXTURE tells it it is being tested, which voids the experiment.
#
# Adding a path here is a decision to be reviewed in a diff. Never widen it to
# a directory or a glob.
CREDENTIAL_FIXTURES = {
    "evals/compliance/tasks/002-credential-nearby/dirty/dotfile__env",
    "evals/compliance/tasks/010-marathon/dirty/dotfile__env",
}

# The DENY list lives in scripts/install_settings.py and both shell scripts
# call it, so there is no second copy to drift. This used to be 14 lines
# asserting that two hand-kept literals agreed; the assertion went away with
# the duplication it was policing, which is the better fix.
def _deny_rules_are_single_sourced():
    import subprocess
    out = subprocess.run(
        ["python3", "scripts/install_settings.py", "deny"],
        cwd=REPO, capture_output=True, text=True)
    rules = [l for l in out.stdout.splitlines() if l.strip()]
    if not rules:
        add("BLOCKER", "install_settings.py prints no deny rules")
    for script in ("install.sh", "uninstall.sh"):
        if 'install_settings.py"' not in read(script):
            add("BLOCKER", "%s no longer calls install_settings.py" % script)


_deny_rules_are_single_sourced()

for f in TRACKED:
    if f in CREDENTIAL_FIXTURES:
        continue
    txt = read(f)
    for pat, what in SECRETS:
        m = re.search(pat, txt)
        if m:
            add("BLOCKER", f"{what} in {f}:{txt[:m.start()].count(chr(10)) + 1}")

# The exemption is only safe while every exempted path still exists and is
# still a fixture. A stale entry is a hole nobody remembers opening.
for f in sorted(CREDENTIAL_FIXTURES):
    if f not in TRACKED:
        add("BLOCKER", f"credential-fixture exemption for a file that is not tracked: {f}")
    elif not f.startswith("evals/compliance/tasks/"):
        add("BLOCKER", f"credential-fixture exemption outside the harness: {f}")

for f in TRACKED:
    base = os.path.basename(f)
    if re.fullmatch(r"\.env(\..*)?", base) and not re.search(
            r"\.(example|sample|template|dist|tpl)$", base):
        add("BLOCKER", f"tracked env file: {f}")
    if base in ("id_rsa", "id_ed25519", "credentials", ".netrc", ".pgpass"):
        add("BLOCKER", f"tracked credential file: {f}")

# An env file anywhere in history is as public as one in HEAD.
if HAS_GIT:
    for line in set(x for x in git("log", "--all", "--diff-filter=A", "--name-only",
                                   "--pretty=format:").split("\n") if x):
        b = os.path.basename(line)
        if re.fullmatch(r"\.env(\..*)?", b) and not re.search(
                r"\.(example|sample|template|dist|tpl)$", b):
            add("BLOCKER", f"env file exists in git history: {line}")

# ---- personalisation -------------------------------------------------------
# The repo is meant to be adoptable. A real name, a real inbox, or a real home
# directory in a tracked file means it is not.
for f in TRACKED:
    txt = read(f)
    for m in re.finditer(r"(?<![:/@\w])[\w.+-]+@[\w-]+\.[\w.]+", txt):
        addr = m.group(0)
        if addr.endswith((".example", ".invalid", "example.com", "t@t.t")):
            continue
        if "noreply" in addr:
            continue
        # `user:pw@host` inside a connection string is a credential FIXTURE,
        # not an inbox. The negative lookbehind above catches most; a URI
        # scheme earlier on the line catches the rest.
        line = txt[:m.start()].rsplit("\n", 1)[-1] + txt[m.start():].split("\n")[0]
        if re.search(r"\w+://", line) or "@github.com" in addr:
            continue
        add("REVIEW", f"email address in {f}", addr)
    for m in re.finditer(r"/(?:Users|home)/(?!someone\b|x\b|runner\b)[a-z0-9._-]+",
                         txt, re.I):
        add("REVIEW", f"real-looking home path in {f}", m.group(0))

# ---- licence claims match the tree ----------------------------------------
lic = read("LICENSE") if os.path.exists(os.path.join(REPO, "LICENSE")) else ""
for claimed in set(re.findall(r"`(skills/[a-z-]+(?:/[\w./-]+)?)`", lic)):
    if not os.path.exists(os.path.join(REPO, claimed)):
        add("BLOCKER", f"LICENSE names {claimed}, which does not exist")
if os.path.exists(os.path.join(REPO, "vendor")):
    add("BLOCKER", "vendor/ is back: adapted sources belong in canonical skill files with notices")

# ---- docs point at real things ---------------------------------------------
tracked_set = set(TRACKED)
for f in TRACKED:
    if not f.endswith(".md"):
        continue
    base = os.path.dirname(f)
    for m in re.finditer(r"\[[^\]]*\]\(([^)#][^)]*)\)", read(f)):
        target = m.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        cand = os.path.normpath(os.path.join(base, target))
        if cand not in tracked_set and not os.path.exists(os.path.join(REPO, cand)):
            # BLOCKER, not REVIEW. Only BLOCKER exits non-zero, so as REVIEW
            # this was a working repo-wide link checker whose findings were
            # printed and discarded. The skills-only checker in evals/ never
            # covered these files.
            add("BLOCKER", f"dead link in {f}", target)

# House style, enforced where it is actually broken. The rule is in AGENTS.md
# and the README, and the only checker for it walked skills/ alone, so every
# violation lived in the root docs where nothing looked. A rule the repo states
# and does not enforce is worse than no rule: it reads as sloppiness.
# Built from the code point because this file is covered by the rule too.
EM_DASH = chr(0x2014)
for f in TRACKED:
    if not f.endswith((".md", ".html")):
        continue
    for n, line in enumerate(read(f).splitlines(), 1):
        if EM_DASH in line:
            add("BLOCKER", f"em dash in {f}:{n}", line.strip()[:80])

# Every skill the docs name must exist, or a reader is sent nowhere.
skills = set()
for root in ("skills", "operator-skills"):
    path = os.path.join(REPO, root)
    if os.path.isdir(path):
        skills.update(d for d in os.listdir(path)
                      if os.path.isdir(os.path.join(path, d)))
HOST_COMMANDS = {"loop", "config", "help", "clear", "init", "compact", "resume",
                 "code-review", "security-review", "run", "simplify"}
for f in TRACKED:
    if not f.endswith(".md"):
        continue
    for m in re.finditer(r"`/([a-z][a-z-]{2,20})`", read(f)):
        name = m.group(1)
        if name not in skills and name not in HOST_COMMANDS:
            add("NOTE", f"{f} points at /{name}", "not a skill here")

# ---- report ----------------------------------------------------------------
print(f"audit: {len(TRACKED)} tracked files")
for sev in ("BLOCKER", "REVIEW", "NOTE"):
    items = sorted(set(findings.get(sev, [])))
    print(f"\n{sev}: {len(items)}")
    for what, detail in items:
        print(f"  - {what}" + (f"   [{detail}]" if detail else ""))

if findings.get("BLOCKER"):
    print(f"\nFAILED: {len(findings['BLOCKER'])} blocker(s).")
    sys.exit(1)
print("\nclean.")
