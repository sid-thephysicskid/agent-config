#!/usr/bin/env python3
import os
import re

from guard_parse import normalize_path, strip_quoted, tokens
from guard_secrets import READ_SAFE_SECRET, _is_secret_path

MIDDLE_SIGNALS = (
    r"\.(claude|codex|cursor)/(hooks|settings\.json|settings\.local\.json|hooks\.json)",
    r"\.git/(config|hooks|HEAD|refs)",
    r"\.local/share/agent-config",
)

_GIT_CONTROL = re.compile(
    r"(^|/)\.git/(config|COMMIT_EDITMSG|HEAD|refs(?:/|$)|hooks(?:/|$))")

# Matched on SHAPE, anywhere. Instruction files (CLAUDE.md, AGENTS.md) are prose and never protected.
GUARD_OWN_FILES = re.compile(r"(^|/)\.(claude|codex|cursor)/hooks(?:/|$)")
# Settings files that wire the guard in: editable, as long as the guard's own hook entries survive.
GUARD_CONFIG = re.compile(
    r"(^|/)\.(claude|codex|cursor)/(settings\.json|settings\.local\.json|hooks\.json)$")
GUARD_HOOK = re.compile(r"guard-(?:bash|files|codex|cursor|prompt)\.py|(?:agent-config|onbelay)-hook-v1")

PAYLOAD_ROOT = "~/.local/share/agent-config"

def _guard_kind(path):
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

_UNMAKE_ALL_ARGS = re.compile(
    r"(^|[\s;&|(])(rm|unlink|mv|shred|truncate|chmod|chown|ln|tee)\b")
_UNMAKE_LAST_ARG = re.compile(r"(^|[\s;&|(])(cp|install|rsync)\b")
_UNMAKE_IN_PLACE = re.compile(
    r"(^|[\s;&|(])(sed\b[^|;&]{0,80}?\s-[a-zA-Z]*i"
    r"|(perl|ruby)\b[^|;&]{0,80}?\s-[a-zA-Z]*i"
    r"|patch\b)")

def check_guard_mutation(seg, line=None):
    text = str(seg)
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
    if isinstance(path, (list, tuple)):
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
        if not writing and READ_SAFE_SECRET.search(p):
            return None
        verb = "write to" if writing else "read"
        return (f"attempt to {verb} '{path}', which holds live credentials.",
                "use the .example variant for variable names. If you need a value set, "
                "ask the human to set it; never read or print the real one.")
    return check_control_path(p, path, change) if writing else None

def check_control_path(p, shown=None, change=None):
    shown = shown or p
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
