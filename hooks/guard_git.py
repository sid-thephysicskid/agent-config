#!/usr/bin/env python3
import os
import re
import subprocess

from guard_repo import (  # noqa: F401
    MAX_GIT_CALLS,
    _GIT_CALLS,
    current_branch,
    has_commits,
    is_branch,
    is_git_repo,
    is_virgin_repo,
    rebase_in_progress,
    reset_state,
)
from guard_parse import (  # noqa: F401
    asks_for_help,
    normalize_path,
    strip_quoted,
    tokens,
)

# Read from the hook's environment (the user's profile), so an agent's `export` cannot change it.
_DEFAULT_PROTECTED = ("main", "master", "trunk", "release", "production", "prod")
_override = os.environ.get("AGENT_CONFIG_PROTECTED_BRANCHES")
PROTECTED_BRANCHES = (
    {b.strip() for b in _override.split(",") if b.strip()}
    if _override is not None else set(_DEFAULT_PROTECTED))
# Opt-in: also refuse plain commits, merges and pushes on the protected set.
BLOCK_DIRECT_COMMITS = os.environ.get("AGENT_CONFIG_BLOCK_DIRECT_COMMITS") == "1"

_PROT_ALT = "|".join(sorted((re.escape(b) for b in PROTECTED_BRANCHES),
                            key=len, reverse=True)) or "(?!)"

MIDDLE_SIGNALS = (
    r"\bgit\b[^\n]{0,80}--force(?![-\w])",
    r"\breset\s+--hard",
    r"\bclean\s+-[\w-]*f",
    r"\bbranch\s+-D",
    r"\bgit\b[^\n]{0,80}\b(commit|push)\b",
    r"\bgit\b[^\n]{0,40}(checkout|restore)\s+(\.|:/|\*)",
    r"\bstash\s+drop",
    r"\bworktree\s+remove\s+[^\n]{0,20}-",
    r"\bfilter-(branch|repo)\b",
    r"\bbranch\s+-[\w-]*f(?![-\w])",
    r"\bcheckout\s+-[\w-]*B(?![-\w])",
)

COMMIT_MAKING = {"commit", "merge", "revert", "cherry-pick", "am"}

_NOT_A_COMMIT_ANY = re.compile(r"--(help)\b|(^|\s)-h(\s|$)")

_NOT_A_COMMIT_BY_VERB = {
    "merge": r"--(continue|abort|quit|ff-only|squash|no-commit)\b|(^|\s)-n(\s|$)",
    "revert": r"--(continue|abort|skip|quit|no-commit)\b|(^|\s)-n(\s|$)",
    "cherry-pick": r"--(continue|abort|skip|quit|no-commit)\b|(^|\s)-n(\s|$)",
    "am": r"--(continue|abort|skip|quit|show-current-patch)\b",
    "commit": r"(?!)",          # nothing exempts a plain commit
}

def _args_after(seg, *verbs):
    toks = tokens(seg)
    kw = next((k for k in verbs if k in toks), None)
    return None if kw is None else toks[toks.index(kw) + 1:]

_REDIRECT = re.compile(r"^\d*(>>?|<<?|>&|&>)")

def _safe_force_with_lease(seg, branch):
    args = _args_after(seg, "push") or []
    lease = [i for i, arg in enumerate(args)
             if arg.startswith("--force-with-lease")]
    if len(lease) != 1 or not branch or branch in PROTECTED_BRANCHES:
        return False
    match = re.fullmatch(
        r"--force-with-lease=([^:]+):([0-9a-fA-F]{40})", args[lease[0]])
    if not match or match.group(1) != branch:
        return False
    rest, skip = [], False
    for i, a in enumerate(args):
        if i == lease[0]:
            continue
        if skip:
            skip = False                     # the target of a bare `>`
            continue
        if _REDIRECT.match(a):
            skip = a in (">", ">>", "<", "&>", "2>")   # operator and target split
            continue
        if a.startswith("-"):
            continue
        rest.append(a)
    for i, arg in enumerate(rest):
        if i == 0 and ":" not in arg:
            continue                                   # the remote
        if arg in (branch, "HEAD:" + branch, branch + ":" + branch):
            continue                                   # this branch, no other
        return False
    return True

def _exempt_from_branch_rule(sub_cmd, seg):
    after = _args_after(seg, sub_cmd)
    if after is not None:
        for stop in ("--", ">", ">>", "<", "|"):
            if stop in after:
                after = after[:after.index(stop)]
        if _NOT_A_COMMIT_ANY.search(" " + " ".join(after) + " "):
            return True
    pat = _NOT_A_COMMIT_BY_VERB.get(sub_cmd)
    return bool(pat and re.search(pat, seg))

VERSION_BUMPER = re.compile(
    r"(^|[\s;&|(])(npm|pnpm|bun)\s+version\s+(?!-)\S(?![^\n]*--no-git-tag-version)"
    r"|(^|[\s;&|(])yarn\s+version\b(?![^\n]*--no-git-tag-version)"
    r"|(^|[\s;&|(])(lerna|nx)\s+version\b"
    r"|(^|[\s;&|(])(standard-version|commit-and-tag-version)\b"
    r"|(^|[\s;&|(])(bumpversion|bump2version)\b"
    r"|(^|[\s;&|(])cargo\s+release\b")

MAX_SEGMENT_SCAN = 8 * 1024

MAX_GIT_INVOCATIONS = 50

def git_invocations(seg):
    toks = tokens(seg)
    found = []
    for i, tok in enumerate(toks):
        if os.path.basename(tok.strip("(){};")) != "git":
            continue
        j = i + 1
        repo = None
        while j < len(toks) and toks[j].startswith("-"):
            t = toks[j]
            if t == "-C" and j + 1 < len(toks):
                repo = toks[j + 1]; j += 2; continue
            if t.startswith("--git-dir="):
                repo = t.split("=", 1)[1]; j += 1; continue
            if t in ("--git-dir", "--work-tree") and j + 1 < len(toks):
                if t == "--git-dir":
                    repo = toks[j + 1]
                j += 2; continue
            if t == "-c" and j + 1 < len(toks):
                j += 2; continue
            j += 1
        if j < len(toks):
            found.append((toks[j], repo))
            if len(found) >= MAX_GIT_INVOCATIONS:
                break
    return found

DRY_RUN_SUBS = ("push", "clean")

def _is_dry_run(seg, sub):
    if sub not in DRY_RUN_SUBS:
        return False
    args = _args_after(seg, sub) or []
    for arg in args:
        if arg == "--":
            return False
        if arg == "--dry-run":
            return True
        # A short cluster: -n, -nd, -xdn, -nf. Not a long option, so one dash.
        if re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", arg):
            return True
    return False

DESTRUCTIVE_GIT = (
    (r"\breset\s+.*--hard", "git reset --hard (discards committed and staged work)",
     "git stash  or  git revert <sha>"),
    (r"\bclean\s+.*-\w*f", "git clean -f (deletes untracked files permanently)",
     "git clean -n first to preview, then delete the specific files you meant"),
    (r"\bbranch\s+(-\w*D\b|--delete\b[^\n]{0,40}--force\b|--force\b[^\n]{0,40}--delete\b)", "git branch -D (force-deletes an unmerged branch)",
     "git branch -d  (refuses if unmerged, which is the point)"),
    (r"\bbranch\s+(-\w*d\b|--delete\b)[^\n]{0,40}(?<![\w./-])(?:" + _PROT_ALT + r")(?![\w./-])",
     "deleting a protected branch",
     "delete the feature branch you meant, or ask the human"),
    (r"\bpush\b[^\n]{0,60}--mirror\b", "git push --mirror (force-updates every ref and deletes remote branches)",
     "push the one branch you mean: git push origin <branch>"),
    (r"\b(filter-branch|filter-repo)\b", "history rewrite", "open a PR and discuss first"),
    (r"\bstash\s+(drop|clear)\b", "dropping stashed work", "git stash list  and apply what you need"),
    (r"\bbranch\s+(-\w*f\b|--force\b)[^\n]{0,40}\b(?:" + _PROT_ALT + r")\b",
     "git branch -f on a protected branch (moves it under everyone else)",
     "branch somewhere else, or open a PR"),
    (r"\b(checkout|switch)\s+(-\w*[BC]\b|--force-create\b)\s+(?:" + _PROT_ALT + r")\b",
     "git checkout -B on a protected branch (resets it to wherever you are)",
     "git checkout <branch> without -B, or use a new branch name"),
    (r"\bworktree\s+remove\s+(.*\s)?-(-force\b|[A-Za-z]*f\b)",
     "force-removing a worktree with live changes",
     "git worktree remove without --force, and commit or stash first"),
)

def _is_whole_tree(tok):
    t = tok.strip().strip("'\"")
    if t in ("*", "*/", ":/", ":", ":/.", ":(top)", ""):
        return True
    if t.startswith(":(") and "top" in t.split(")")[0]:
        return True
    t = t.rstrip("/") or "."
    return os.path.normpath(t) in (".", "..")

def _checkout_target(seg):
    rest = _args_after(seg, "checkout", "switch")
    if rest is None:
        return None
    if "--detach" in rest or "-d" in rest:
        return None
    if "--" in rest:
        return None
    names = [x for x in rest if not x.startswith("-")]
    if len(names) != 1:
        return None
    # No quote-stripping: the caller strips every quote before this runs.
    name = names[0]
    # A SHA, a path, or a remote-tracking ref is not a branch to trust.
    if "~" in name or "^" in name or ":" in name:
        return None
    return name

def _checkout_touches_worktree(seg):
    rest = _args_after(seg, "checkout", "switch")
    if not rest:
        return False
    # `git checkout -b x` and `git checkout <branch>` are not path operations.
    if any(x in ("-b", "-B", "--orphan") for x in rest):
        return False
    if any(x in ("-f", "--force", "--discard-changes") or
           (re.fullmatch(r"-[A-Za-z]+", x) and "f" in x[1:]) for x in rest):
        return True
    paths = [x for x in rest if not x.startswith("-") and x != "--"]
    # a bare `git checkout <ref>` names one ref, not a pathspec
    if "--" not in rest and len(paths) == 1 and not _is_whole_tree(paths[0]):
        return False
    return any(_is_whole_tree(x) for x in paths)

def _restore_touches_worktree(seg):
    rest = _args_after(seg, "restore")
    if rest is None:
        return False
    paths = [x for x in rest if not x.startswith("-") and x != "--"]
    if not any(_is_whole_tree(x) for x in paths):
        return False
    staged = worktree = False
    for x in rest:
        if x == "--staged" or (re.fullmatch(r"-[A-Za-z]+", x) and "S" in x[1:]):
            staged = True
        if x == "--worktree" or (re.fullmatch(r"-[A-Za-z]+", x) and "W" in x[1:]):
            worktree = True
    return worktree or not staged

def check_git(seg, cwd, branch_override=None, unknown_cwd=False, virgin_dirs=()):
    if len(seg) > MAX_SEGMENT_SCAN:
        seg = seg[:MAX_SEGMENT_SCAN]
    if asks_for_help(seg):
        return None
    calls = git_invocations(seg)
    if not calls:
        if not any(w in seg for w in ("version", "release", "bump")):
            return None
        if BLOCK_DIRECT_COMMITS and VERSION_BUMPER.search(seg) \
                and not unknown_cwd and is_git_repo(cwd) \
                and current_branch(cwd) in PROTECTED_BRANCHES:
            return ("a version bump that commits and tags, on a protected branch.",
                    "bump on your feature branch, or cut the release from the "
                    "merge commit: gh release create <tag> --target <base>")
        return None

    if re.search(r"(^|\s)GIT_DIR=", getattr(seg, "raw", seg)):
        unknown_cwd = True

    push_scanned = False
    for sub, repo in calls:
        # Resolve -C against the PAYLOAD cwd, not the hook process cwd.
        target = os.path.join(cwd, normalize_path(repo)) if repo else cwd
        target = os.path.normpath(target)
        unresolved_repo = bool(repo) and bool(re.search(r"[$`*?]", repo))
        if unresolved_repo:
            unknown_cwd = True
        if unknown_cwd and (not repo or unresolved_repo):
            branch = None      # unknown fails closed below
        elif not is_git_repo(target):
            branch = None
        else:
            branch = branch_override if (branch_override and not repo) else current_branch(target)

        no_repo = not unknown_cwd and not is_git_repo(target)
        # Unknown branch: a commit is local and reversible, so only a push fails closed.
        on_protected = not no_repo and branch in PROTECTED_BRANCHES

        if sub == "commit" and branch == "HEAD" and not no_repo \
                and not rebase_in_progress(target) \
                and not (target in virgin_dirs or is_virgin_repo(target)):
            return ("commit on a detached HEAD (the commit is orphaned by the next checkout).",
                    "git bisect reset, or git checkout -b fix/<name> to keep the work")

        if BLOCK_DIRECT_COMMITS and sub in COMMIT_MAKING and on_protected \
                and not _exempt_from_branch_rule(sub, strip_quoted(seg)) \
                and not (target in virgin_dirs or is_virgin_repo(target)):
            verb = "commit" if sub == "commit" else f"`git {sub}`"
            return (f"{verb} directly to '{branch}'.",
                    "git checkout -b feature/<name>   (branch there, then open a PR)")

        if sub == "push":
            if _is_dry_run(seg, sub):
                continue
            seg = re.sub(r"(^|[\s+:])refs/heads/", r"\1",
                         seg.replace('"', "").replace("'", ""))
            push_args = _args_after(seg, "push") or []
            if "--all" in push_args:
                return ("git push --all (can update a protected branch that is not checked out).",
                        "push the one feature branch you mean: git push -u origin <branch>")
            if any(arg.startswith("--force-with-lease") for arg in push_args) \
                    and not _safe_force_with_lease(seg, branch):
                return ("an unpinned or mismatched force-with-lease push.",
                        "use git push --force-with-lease=<current-branch>:<full-before-sha> "
                        "after inspecting your own open PR branch")
            if re.search(r"--force(?![-\w])", seg) or re.search(r"(?<![\w-])-\w*f\w*(?=\s|$)", seg):
                return ("force push.",
                        "git push --force-with-lease  (allowed on your own PR branch, never on a protected one)")
            if re.search(r"(^|[\s'\"])\+[\w./-]", seg):
                return ("force push by refspec (the leading + forces it).",
                        "push normally, or --force-with-lease on your own branch")
            deleting = "--delete" in push_args or "-d" in push_args
            for b in (() if push_scanned else PROTECTED_BRANCHES):
                if (":" + b) in push_args or (deleting and b in push_args):
                    return (f"deleting the remote '{b}' branch.",
                            "delete a feature branch instead, or ask the human")
                if not BLOCK_DIRECT_COMMITS:
                    continue
                if re.search(rf":{re.escape(b)}(\s|$)", seg):
                    return (f"pushing directly to '{b}' by refspec.", "open a PR instead")
                # `git push origin main` from anywhere
                if re.search(rf"\bpush\b[^|;]*\s{re.escape(b)}(\s|$)", seg) and "HEAD:" not in seg:
                    return (f"pushing directly at '{b}'.",
                            "push your feature branch and open a PR")
            push_scanned = True
            if BLOCK_DIRECT_COMMITS and (on_protected or (branch is None and not no_repo)):
                where = branch or "an undeterminable branch"
                return (f"push from '{where}'.",
                        "push a feature branch and open a PR: git push -u origin feature/<name>")

        if sub in ("checkout", "switch") and _checkout_touches_worktree(seg):
            return ("git checkout . (discards all local changes)",
                    "git stash  to keep the changes recoverable")

        if sub == "restore" and _restore_touches_worktree(seg):
            return ("git restore . (discards all local changes)",
                    "git restore --staged .  if you only meant to unstage, "
                    "or git stash to keep the changes recoverable")

        scan = strip_quoted(seg) if sub in (
            "commit", "tag", "notes", "log", "show", "grep", "blame") else seg
        if _is_dry_run(seg, sub):
            continue
        for pat, what, fix in DESTRUCTIVE_GIT:
            if re.search(pat, scan):
                return (what, fix)
    return None

NEW_BRANCH = re.compile(
    r"\bgit\b.*\b(?:checkout|switch)\s+(?:--?[\w-]+(?:=\S+)?\s+)*"
    r"-\w*(?:b|c)\s+[\"\']?(?P<br>[\w./-]+)")

def _note_git_init(seg, base, virgin_dirs):
    for sub_cmd, repo in git_invocations(strip_quoted(seg)):
        if sub_cmd != "init":
            continue
        toks = tokens(strip_quoted(seg))
        positional = None
        if "init" in toks:
            takes_value = {"-b", "--initial-branch", "--template",
                           "--separate-git-dir", "--object-format", "--ref-format"}
            rest, skip = [], False
            for x in toks[toks.index("init") + 1:]:
                if skip:
                    skip = False
                    continue
                if x in takes_value:
                    skip = True
                    continue
                if x.startswith("-"):
                    continue
                rest.append(x)
            positional = rest[0] if rest else None
        where = repo or positional
        target = os.path.normpath(os.path.join(base, normalize_path(where))) \
            if where else base
        if not (is_git_repo(target) and has_commits(target)):
            virgin_dirs.add(target)

def _note_checkout(seg, here, unknown_cwd, branch_override):
    if not any(s in ("checkout", "switch") for s, _ in git_invocations(seg)):
        return branch_override
    unquoted = seg.replace('"', "").replace("'", "")
    nb = NEW_BRANCH.search(unquoted)
    if nb:
        return nb.group("br")
    cand = _checkout_target(unquoted)
    return cand if (cand and not unknown_cwd and is_branch(here, cand)) else None
