#!/usr/bin/env python3
"""Rules for a PATH, as opposed to a command.

A separate entry point with a separate adapter: `guard-files.py` asks
`check_path` and never touches `check_command`. Two questions live here, and
keeping them apart matters because a shell redirect asks the second and not the
first:

  IS THIS A CREDENTIAL   handled by guard_secrets, with all its exemptions.
                         `cat .env.example > .env` is the sanctioned way to
                         create your env file and must keep working.

  DOES WRITING THIS HAND  .git internals and the guard's own files. Writing
  OVER CONTROL            these does not store data, it changes what a later
                          command will do.

Python 3.9, stdlib only.
"""
import os
import re

from guard_parse import normalize_path, strip_quoted, tokens
from guard_secrets import READ_SAFE_SECRET, _is_secret_path

# Worth finding in the middle of an oversized command line. Every other rule
# module exports one of these and guard_paths did not, so a control-path write
# buried past the 32KB analysis cap fell straight through: `rm` of a guard hook
# blocked on its own and was allowed with 40KB of padding in front of it. The
# fail-closed timeout path in guard_adapter consults the same union, so the
# gap also turned a slow-input attack on the guard's own files from
# fail-closed into fail-open.
MIDDLE_SIGNALS = (
    r"\.(claude|codex)/(hooks|settings\.json|settings\.local\.json|hooks\.json)",
    r"\.git/(config|hooks|HEAD|refs)",
    r"\.local/share/agent-config",
)

_GIT_CONTROL = re.compile(
    r"(^|/)\.git/(config|COMMIT_EDITMSG|HEAD|refs(?:/|$)|hooks(?:/|$))")

# Matched on SHAPE, anywhere. Instruction files (CLAUDE.md, AGENTS.md) are prose and never protected.
GUARD_OWN_FILES = re.compile(r"(^|/)\.(claude|codex)/hooks(?:/|$)")
# Settings files that wire the guard in: editable, as long as the guard's own hook entries survive.
GUARD_CONFIG = re.compile(
    r"(^|/)\.(claude|codex)/(settings\.json|settings\.local\.json|hooks\.json)$")
GUARD_HOOK = re.compile(r"guard-(?:bash|files|codex)\.py|(?:agent-config|onbelay)-hook-v1")


# The npm install, which the README recommends, COPIES the payload to
# ~/.local/share/agent-config/<version>/ and leaves ~/.claude/hooks/*.py as
# symlinks into it. Protecting only the symlink location protected only the
# spelling nobody uses: `rm ~/.claude/hooks/guard_rules.py` was refused while
# `rm -rf ~/.local/share/agent-config` removed the whole guard and was
# allowed. An agent does not have to be clever to land on the real path;
# `readlink -f` is an ordinary command and every editor resolves symlinks on
# its own. And because the hook shim exits 0 when its file is missing, the
# result is a machine with no guard and no message saying so.
#
# Hardcoded rather than read from XDG_DATA_HOME because bin/agent-config.js:44
# and install.sh:313 both hardcode it too. If that ever becomes configurable,
# this has to move with it.
PAYLOAD_ROOT = "~/.local/share/agent-config"


def _guard_kind(path):
    """'script' for the guard's own code, 'config' for a settings file that wires it in, else None."""
    for payload in (PAYLOAD_ROOT, "~/.local/share/onbelay"):
        payload, expanded = normalize_path(payload), normalize_path(path)
        if expanded == payload or expanded.startswith(payload + "/"):
            return "script"
    if GUARD_OWN_FILES.search(path):
        return "script"
    if GUARD_CONFIG.search(path):
        return "config"
    roots = (
        ("CLAUDE_CONFIG_DIR", "~/.claude", ("settings.json", "settings.local.json")),
        ("CODEX_HOME", "~/.codex", ("hooks.json",)),
    )
    for variable, default, config in roots:
        root = os.environ.get(variable) or default
        expanded = path.replace("${%s}" % variable, root).replace("$%s" % variable, root)
        expanded = normalize_path(expanded)
        base = normalize_path(root)
        if expanded == base + "/hooks" or expanded.startswith(base + "/hooks/"):
            return "script"
        if any(expanded == base + "/" + name for name in config):
            return "config"
    return None


def _drops_guard_hooks(p, change):
    """Would this file-tool change remove or alter the guard's hook entries? Unknown content counts as yes."""
    if not isinstance(change, dict):
        return True
    if isinstance(change.get("patch"), str):
        return bool(re.search(r"^-.*(?:%s)|^\*\*\* Delete File:" % GUARD_HOOK.pattern,
                              change["patch"], re.M))
    olds = [change.get("old_string")] + [
        e.get("old_string") for e in change.get("edits") or () if isinstance(e, dict)]
    olds = [o for o in olds if isinstance(o, str)]
    if "content" in change:
        try:
            with open(p, encoding="utf-8") as fh:
                current = fh.read()
        except (OSError, ValueError):
            current = ""
        return bool(set(GUARD_HOOK.findall(current))
                    - set(GUARD_HOOK.findall(str(change["content"]))))
    return not olds or any(GUARD_HOOK.search(o) for o in olds)


# Commands that unmake or overwrite a file. Writing to the guard is caught by
# the path rules; deleting, moving or copying over it is the same act with a
# different verb, and `rm ~/.claude/hooks/guard-bash.py` was allowed.
#
# Two shapes, because they answer "which argument is the target" differently.
# `cp SRC DEST` writes only its last argument, and reading the guard's own
# rules is legitimate, so `cp .git/hooks/pre-commit /tmp/backup` must stay
# allowed while `cp /tmp/x .git/hooks/pre-commit` must not.
_UNMAKE_ALL_ARGS = re.compile(
    r"(^|[\s;&|(])(rm|unlink|mv|shred|truncate|chmod|chown|ln|tee)\b")
_UNMAKE_LAST_ARG = re.compile(r"(^|[\s;&|(])(cp|install|rsync)\b")
# In-place editors. Without the flag these READ and write to stdout, which
# is legitimate; with it they rewrite the file, which is the same act as
# tee. `sed -i` is the commonest way an agent edits a file from a shell,
# and it was the one verb missing from the two lists above.
_UNMAKE_IN_PLACE = re.compile(
    r"(^|[\s;&|(])(sed\b[^|;&]{0,80}?\s-[a-zA-Z]*i"
    r"|(perl|ruby)\b[^|;&]{0,80}?\s-[a-zA-Z]*i"
    r"|patch\b)")


def check_guard_mutation(seg, line=None):
    """Deleting, moving or overwriting a file that grants control.

    `uninstall.sh` is unaffected: the hook sees `bash uninstall.sh`, and the
    removals happen inside it, where no tool call exists to inspect.
    """
    text = str(seg)
    # The VERB has to be real shell, not prose inside an argument. Searching
    # the raw text meant any string that merely mentioned one armed the rule,
    # and then every token in the segment became a candidate target: filing a
    # bug that quoted an installer's own `mv` output was refused as an `mv`,
    # and so was writing a test whose fixture text mentions a config path. The
    # guard blocked the work of fixing the guard.
    #
    # Targets are still read from the FULL text, so `rm "~/.claude/settings.json"`
    # with a quoted path stays refused. `bash -c '...'` is unaffected because
    # segments() unwraps the payload into its own segment, where the verb is
    # no longer quoted.
    shell = strip_quoted(text)
    all_args = bool(_UNMAKE_ALL_ARGS.search(shell)
                    or _UNMAKE_IN_PLACE.search(shell))
    last_arg = bool(_UNMAKE_LAST_ARG.search(shell))
    if not (all_args or last_arg):
        return None
    args = [t for t in tokens(text) if not t.startswith("-")]
    targets = args if all_args else args[-1:]
    # In place (`sed -i`, or `jq ... > tmp && mv tmp settings.json`) keeps the file; allowed unless it names the hooks.
    verbs = {m.group(2) for m in _UNMAKE_ALL_ARGS.finditer(shell)}
    whole = str(line or text)
    in_place = not last_arg and (verbs <= {"mv"} if re.search(r"(^|[\s;&|(])jq\b", whole) else not verbs)
    for tok in targets:
        p = normalize_path(tok.strip("'\""))
        kind = _guard_kind(p)
        if kind == "config" and in_place and not re.search(r"hook|guard", whole, re.I):
            continue
        if kind or _GIT_CONTROL.search(p):
            return (f"removing or overwriting '{tok}', which grants control "
                    "rather than storing data.",
                    "if a rule is wrong, change it in the repo and tell the human; "
                    "./uninstall.sh is the supported way to remove the guard")
    return None


def check_path(path, writing, change=None):
    """Rules for reading or writing a file path. `change` is the file tool's input. Returns (reason, fix) or None."""
    if isinstance(path, (list, tuple)):
        # Every element, not the first. Taking path[0] made the verdict depend
        # on ORDER, so a secret in second position was invisible while the same
        # two paths swapped blocked. Both adapters happen to iterate, which is
        # the only reason this never shipped as a hole.
        for one in path:
            hit = check_path(one, writing, change)
            if hit:
                return hit
        return None
    if not path or not isinstance(path, str):
        return None
    p = normalize_path(path)
    if len(p) > 512:
        p = p[-512:]
    if _is_secret_path(p):
        # Reading one of the non-credential files inside a credential directory
        # is allowed; writing it is not. See READ_SAFE_SECRET.
        if not writing and READ_SAFE_SECRET.search(p):
            return None
        verb = "write to" if writing else "read"
        return (f"attempt to {verb} '{path}', which holds live credentials.",
                "use the .example variant for variable names. If you need a value set, "
                "ask the human to set it; never read or print the real one.")
    return check_control_path(p, path, change) if writing else None


def check_control_path(p, shown=None, change=None):
    """Writes that hand over control rather than storing data.

    Kept apart from the credential rules because a shell redirect asks this
    question and NOT that one: `cat .env.example > .env` is the sanctioned way
    to create your env file, and the secret rules already carry the exemptions
    that make it work.
    """
    shown = shown or p
    # `hooks/` was missing, and it is the one subdirectory of .git that
    # EXECUTES. A pre-commit script written here runs on the next commit, with
    # no tool call of its own for anything to inspect.
    if _GIT_CONTROL.search(p):
        return (f"direct write into .git internals ('{shown}').",
                "use the matching git command instead of editing plumbing by hand")
    kind = _guard_kind(p)
    if kind == "script":
        return (f"write to '{shown}', which is the guard's own code.",
                "if a rule is wrong, change it in the repo and re-run install.sh, "
                "and tell the human rather than editing the installed copy")
    if kind == "config" and _drops_guard_hooks(p, change):
        return (f"write to '{shown}' that could remove the guard's own hook entries.",
                "use Edit on the setting you mean and leave the guard's hook entries in place")
    return None
